"""
ADELE — Tool Registry
=========================
Decorated Python functions that the LLM can invoke by name.
Each tool auto-registers into the global registry and exports
its schema in Gemini function_declarations format.

Every tool declaration automatically includes a `reasoning` argument
so the LLM must explain *why* it is calling the tool.  The reasoning
string is stripped before execution (tools never see it).
"""

import asyncio
import contextvars
import json
import re
import subprocess
import time as _time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Any, Optional

from tools.contracts import error_envelope
from reliability import (
    capture_pre_action_context,
    should_retry_tool,
    verify_post_action_change,
    with_timeout_retry,
)


# ═══════════════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════════════

# Default timeout for tool execution (seconds).
# Individual tools can override via the `timeout` decorator kwarg.
DEFAULT_TOOL_TIMEOUT: float = 60.0

# Maximum allowed timeout (prevents accidental infinite waits).
MAX_TOOL_TIMEOUT: float = 300.0


# ═══════════════════════════════════════════════════════════════
#  Reasoning injection — auto-appended to every tool declaration
# ═══════════════════════════════════════════════════════════════

_REASONING_PROPERTY: dict = {
    "reasoning": {
        "type": "string",
        "description": (
            "One sentence explaining WHY you are calling this tool right now "
            "and what you expect the result to be. REQUIRED."
        ),
    }
}

# Tools that do not need a reasoning argument (communication tools)
_REASONING_EXEMPT_TOOLS: frozenset[str] = frozenset({
    "send_response", "await_reply",
})

_AUTOMATION_CURSOR_CALLBACK: contextvars.ContextVar = contextvars.ContextVar(
    "adele_automation_cursor_callback",
    default=None,
)

_TOOL_EVENT_CALLBACK: contextvars.ContextVar = contextvars.ContextVar(
    "adele_tool_event_callback",
    default=None,
)

_TASK_ID: contextvars.ContextVar = contextvars.ContextVar(
    "adele_task_id",
    default="",
)

_ACTION_SEQ: contextvars.ContextVar = contextvars.ContextVar(
    "adele_action_seq",
    default=0,
)

_CURSOR_TOOL_NAMES: frozenset[str] = frozenset({
    "click_element",
    "click_ui",
    "type_in_field",
    "type_text",
    "press_key",
    "run_shortcut",
    "open_app",
    "open_url",
    "browser_click_ref",
    "browser_click_match",
    "browser_type_ref",
    "browser_select_ref",
    "mouse_action",
})

_POST_VERIFY_TOOLS: frozenset[str] = frozenset({
    "click_ui",
    "type_in_field",
    "click_element",
    "open_app",
    "open_url",
    "browser_click_ref",
    "browser_click_match",
    "browser_type_ref",
    "browser_select_ref",
})


def set_tool_run_context(task_id: str = "", cb=None) -> None:
    """Set request-scoped IDs/callbacks used to tag every tool event."""
    _TASK_ID.set(str(task_id or ""))
    _ACTION_SEQ.set(0)
    _TOOL_EVENT_CALLBACK.set(cb)


def set_automation_cursor_callback(cb) -> None:
    """Set the async callback used to mirror desktop automation in the overlay."""
    _AUTOMATION_CURSOR_CALLBACK.set(cb)


def current_task_id() -> str:
    return _TASK_ID.get("") or ""


def _next_action_id(tool_name: str) -> str:
    seq = int(_ACTION_SEQ.get(0) or 0) + 1
    _ACTION_SEQ.set(seq)
    task_id = current_task_id()
    safe_tool = re.sub(r"[^a-zA-Z0-9_]+", "_", str(tool_name or "tool")).strip("_")[:32]
    if task_id:
        return f"{task_id}:a{seq:03d}:{safe_tool}"
    return f"adhoc-{uuid.uuid4().hex[:8]}:a{seq:03d}:{safe_tool}"


def _result_preview(value: Any, limit: int = 700) -> str:
    text = str(value or "")
    text = text.replace("\r", "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _event_ok_from_result_text(result_text: str) -> bool:
    try:
        parsed = json.loads(result_text)
    except Exception:
        return True
    if isinstance(parsed, dict) and parsed.get("ok") is False:
        return False
    return True


async def _emit_tool_event(payload: dict) -> None:
    cb = _TOOL_EVENT_CALLBACK.get(None)
    if not cb:
        return
    try:
        event = {
            "type": "tool_event",
            "taskId": current_task_id(),
            **payload,
        }
        await cb(event)
    except Exception:
        pass


async def _emit_automation_cursor(payload: dict) -> None:
    cb = _AUTOMATION_CURSOR_CALLBACK.get(None)
    if not cb:
        return
    try:
        await cb({
            "type": "automation_cursor",
            "taskId": current_task_id(),
            "payload": payload,
        })
    except Exception:
        pass


def _coerce_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _first_coordinate_pair(text: str) -> Optional[tuple[int, int]]:
    match = re.search(r"\((\d{1,5})\s*,\s*(\d{1,5})\)", str(text or ""))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _browser_ref_cursor_payload(name: str, args: dict, label: str) -> Optional[dict]:
    ref_id = str(args.get("ref_id") or "").strip()
    if not ref_id:
        return None

    try:
        from browser.store import browser_store
    except Exception:
        return None

    try:
        snapshot = browser_store.get_snapshot(str(args.get("session_id") or "") or None)
        if snapshot is None:
            return None
        element = browser_store.get_element(ref_id, snapshot.session_id) or browser_store.get_element(ref_id, None)
    except Exception:
        return None

    if not element:
        return None

    bounds = dict(element.bounds or {})
    x = bounds.get("mid_x", bounds.get("x"))
    y = bounds.get("mid_y", bounds.get("y"))
    if x is None or y is None:
        return None

    title_by_tool = {
        "browser_click_ref": "Target grounded",
        "browser_type_ref": "Text field grounded",
        "browser_select_ref": "Dropdown grounded",
    }
    meta_bits = [element.primary_label() or ref_id]
    role = element.role or element.tag
    if role:
        meta_bits.append(role)

    return {
        "action": "move",
        "x": _coerce_int(x),
        "y": _coerce_int(y),
        "label": label,
        "title": title_by_tool.get(name, "Browser target grounded"),
        "meta": " - ".join(str(bit) for bit in meta_bits if bit),
        "source": "browser snapshot",
        "ref_id": ref_id,
        "target": {
            "ref_id": ref_id,
            "label": element.primary_label(),
            "role": role,
            "bounds": bounds,
            "source": "browser snapshot",
        },
        "autoHideMs": 0,
    }


async def _emit_cursor_before_tool(name: str, args: dict) -> None:
    if name in {
        "click_ui",
        "type_in_field",
        "type_text",
        "press_key",
        "run_shortcut",
        "open_app",
        "open_url",
        "browser_click_ref",
        "browser_click_match",
        "browser_type_ref",
        "browser_select_ref",
    }:
        label_by_tool = {
            "click_ui": "FIND",
            "type_in_field": "TYPE",
            "type_text": "TYPE",
            "press_key": "KEY",
            "run_shortcut": "KEY",
            "open_app": "OPEN",
            "open_url": "OPEN",
            "browser_click_ref": "CLICK",
            "browser_click_match": "CLICK",
            "browser_type_ref": "TYPE",
            "browser_select_ref": "SELECT",
        }
        if name in {"browser_click_ref", "browser_type_ref", "browser_select_ref"}:
            payload = _browser_ref_cursor_payload(name, args, label_by_tool.get(name, "TARGET"))
            if payload:
                await _emit_automation_cursor(payload)
                await asyncio.sleep(0.35)
                return
        await _emit_automation_cursor({
            "action": "move",
            "x": 0,
            "y": 0,
            "label": label_by_tool.get(name, "ADELE"),
            "title": "Finding target",
            "meta": name,
            "position": "center",
            "autoHideMs": 5200,
        })
        return

    if name == "click_element":
        await _emit_automation_cursor({
            "action": "move",
            "x": _coerce_int(args.get("x")),
            "y": _coerce_int(args.get("y")),
            "label": "ADELE",
            "title": "Pointing to coordinates",
            "meta": f"{_coerce_int(args.get('x'))}, {_coerce_int(args.get('y'))}",
            "autoHideMs": 5200,
        })
        await asyncio.sleep(0.45)
        return

    if name == "mouse_action":
        action = str(args.get("action", "")).lower()
        if action == "move":
            await _emit_automation_cursor({
                "action": "move",
                "x": _coerce_int(args.get("x")),
                "y": _coerce_int(args.get("y")),
                "label": "MOVE",
            })
        elif action == "drag":
            await _emit_automation_cursor({
                "action": "drag",
                "x": _coerce_int(args.get("x")),
                "y": _coerce_int(args.get("y")),
                "x2": _coerce_int(args.get("x2")),
                "y2": _coerce_int(args.get("y2")),
                "label": "DRAG",
            })


async def _emit_cursor_after_tool(name: str, args: dict, result: Any) -> None:
    result_text = str(result or "")
    if name == "click_element":
        click_type = str(args.get("click_type", "single")).lower()
        await _emit_automation_cursor({
            "action": "double" if click_type == "double" else ("right" if click_type == "right" else "click"),
            "x": _coerce_int(args.get("x")),
            "y": _coerce_int(args.get("y")),
            "label": click_type.upper() if click_type in {"double", "right"} else "CLICK",
        })
        return

    if name in {"click_ui", "type_in_field"}:
        coords = _first_coordinate_pair(result_text)
        if coords:
            await _emit_automation_cursor({
                "action": "click",
                "x": coords[0],
                "y": coords[1],
                "label": "CLICK" if name == "click_ui" else "TYPE",
                "autoHideMs": 5200,
            })
        return

    if name in {"browser_click_ref", "browser_type_ref", "browser_select_ref"}:
        label_by_tool = {
            "browser_click_ref": "CLICK",
            "browser_type_ref": "TYPE",
            "browser_select_ref": "SELECT",
        }
        action_by_tool = {
            "browser_click_ref": "click",
            "browser_type_ref": "type",
            "browser_select_ref": "click",
        }
        payload = _browser_ref_cursor_payload(name, args, label_by_tool.get(name, "TARGET"))
        if payload:
            payload["action"] = action_by_tool.get(name, "click")
            payload["title"] = "Acting on target"
            payload["autoHideMs"] = 5200
            await _emit_automation_cursor(payload)


# ═══════════════════════════════════════════════════════════════
#  Tool Registry Infrastructure
# ═══════════════════════════════════════════════════════════════

@dataclass
class ToolDef:
    """Metadata for a registered tool."""
    name: str
    description: str
    parameters: dict          # JSON-schema style
    func: Callable            # The actual async function
    timeout: float = DEFAULT_TOOL_TIMEOUT  # Per-tool timeout in seconds
    reasoning_exempt: bool = False  # If True, no reasoning arg injected


class ToolRegistry:
    """Holds all available tools and serializes them for Gemini."""

    def __init__(self):
        self._tools: dict[str, ToolDef] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        timeout: float = DEFAULT_TOOL_TIMEOUT,
        reasoning_exempt: bool = False,
    ):
        """Decorator to register a tool function.
        
        Args:
            name: Tool name visible to the LLM.
            description: Tool description.
            parameters: JSON-schema style parameter spec.
            timeout: Max seconds the tool may run before being cancelled.
            reasoning_exempt: If True, no ``reasoning`` arg is injected.
        """
        _timeout = min(max(1.0, float(timeout)), MAX_TOOL_TIMEOUT)
        def decorator(func: Callable):
            self._tools[name] = ToolDef(
                name=name,
                description=description,
                parameters=parameters,
                func=func,
                timeout=_timeout,
                reasoning_exempt=reasoning_exempt,
            )
            return func
        return decorator

    async def execute(self, name: str, args: dict) -> str:
        """Execute a tool by name with given arguments.

        The ``reasoning`` key is silently stripped from *args* so tool
        functions never need to accept it.  Returns result string.

        Enforces a per-tool timeout to prevent hung tools from blocking
        the agent indefinitely.
        """
        tool = self._tools.get(name)
        action_id = _next_action_id(name)
        t_start = _time.time()
        if not tool:
            result = str(error_envelope(
                code="tool.not_found",
                message=f"Unknown tool '{name}'",
            ))
            await _emit_tool_event({
                "phase": "result",
                "actionId": action_id,
                "tool": name,
                "ok": False,
                "durationMs": 0,
                "result": result,
            })
            return result
        try:
            clean_args = {k: v for k, v in args.items() if k != "reasoning"}
            pre_action_ctx = None
            await _emit_tool_event({
                "phase": "start",
                "actionId": action_id,
                "tool": name,
                "args": clean_args,
            })
            if name in _CURSOR_TOOL_NAMES:
                await _emit_cursor_before_tool(name, clean_args)
            if name in _POST_VERIFY_TOOLS:
                try:
                    pre_action_ctx = await capture_pre_action_context(name)
                except Exception:
                    pre_action_ctx = None

            async def _run_tool_once():
                return await tool.func(**clean_args)

            if should_retry_tool(name):
                result = await with_timeout_retry(
                    f"tool:{name}",
                    _run_tool_once,
                    timeout_s=tool.timeout,
                    attempts=2,
                )
            else:
                result = await asyncio.wait_for(
                    _run_tool_once(),
                    timeout=tool.timeout,
                )
            if name in _CURSOR_TOOL_NAMES:
                await _emit_cursor_after_tool(name, clean_args, result)
            result_text = str(result)
            if pre_action_ctx is not None:
                try:
                    verification = await verify_post_action_change(name, result_text, pre_action_ctx)
                except Exception as verify_error:
                    verification = None
                    await _emit_tool_event({
                        "phase": "verification_error",
                        "actionId": action_id,
                        "tool": name,
                        "ok": False,
                        "result": str(verify_error)[:240],
                    })
                if verification and not verification.changed:
                    await _emit_tool_event({
                        "phase": "paused",
                        "actionId": action_id,
                        "tool": name,
                        "ok": False,
                        "message": (
                            f"Paused: {name} completed, but ADELE could not confirm any visible change."
                        ),
                        "details": verification.details,
                    })
                    result_text = str(error_envelope(
                        code="tool.no_visible_change",
                        message=verification.message,
                        retryable=True,
                        details={
                            "tool": name,
                            "source": verification.source,
                            **verification.details,
                        },
                        flatten_details=True,
                    ))
            await _emit_tool_event({
                "phase": "result",
                "actionId": action_id,
                "tool": name,
                "ok": _event_ok_from_result_text(result_text),
                "durationMs": int((_time.time() - t_start) * 1000),
                "result": _result_preview(result_text),
            })
            return result_text
        except asyncio.TimeoutError:
            result = str(error_envelope(
                code="tool.timeout",
                message=f"Tool '{name}' timed out after {tool.timeout:.0f}s",
                retryable=True,
            ))
            await _emit_tool_event({
                "phase": "result",
                "actionId": action_id,
                "tool": name,
                "ok": False,
                "durationMs": int((_time.time() - t_start) * 1000),
                "result": result,
            })
            return result
        except TypeError as e:
            result = str(error_envelope(
                code="tool.invalid_args",
                message=f"Invalid arguments for '{name}': {e}",
            ))
            await _emit_tool_event({
                "phase": "result",
                "actionId": action_id,
                "tool": name,
                "ok": False,
                "durationMs": int((_time.time() - t_start) * 1000),
                "result": result,
            })
            return result
        except Exception as e:
            result = str(error_envelope(
                code="tool.execution_error",
                message=f"Error executing {name}: {e}",
                retryable=True,
            ))
            await _emit_tool_event({
                "phase": "result",
                "actionId": action_id,
                "tool": name,
                "ok": False,
                "durationMs": int((_time.time() - t_start) * 1000),
                "result": result,
            })
            return result

    def declarations(self, exclude: Optional[set] = None) -> list[dict]:
        """Export tools in Gemini function_declarations format.

        Automatically injects the ``reasoning`` property into every
        non-exempt tool so the LLM is forced to justify each call.

        Args:
            exclude: Optional set of tool names to omit from the list.
                     Excluded tools remain callable via ``execute()``
                     but won't appear in the LLM's schema.
        """
        _exclude = exclude or set()
        decls = []
        for t in self._tools.values():
            if t.name in _exclude:
                continue
            params = dict(t.parameters) if t.parameters else {"type": "object", "properties": {}}
            is_exempt = t.reasoning_exempt or t.name in _REASONING_EXEMPT_TOOLS
            if not is_exempt:
                # Deep-copy properties and inject reasoning
                props = dict(params.get("properties", {}))
                props.update(_REASONING_PROPERTY)
                params = {**params, "properties": props}
                # Add reasoning to required list
                required = list(params.get("required", []))
                if "reasoning" not in required:
                    required.append("reasoning")
                params["required"] = required
            decls.append({
                "name": t.name,
                "description": t.description,
                "parameters": params,
            })
        return decls

    def list_names(self) -> list[str]:
        return list(self._tools.keys())


# ── Global registry instance ──
registry = ToolRegistry()


# ═══════════════════════════════════════════════════════════════
#  Helper: run AppleScript
# ═══════════════════════════════════════════════════════════════

async def _osascript(script: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace").strip()
        return f"AppleScript error: {err}"
    return stdout.decode("utf-8", errors="replace").strip()
