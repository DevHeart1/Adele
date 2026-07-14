"""
ADELE local action contract.

This module ports the TipTour-style desktop action loop into Adele's
Electron/Windows backend:

    observe -> visual_context -> ground_target -> act -> validate

The contract is deliberately stricter than the free-form agent loop. It keeps a
trace_id on every step, accepts one action per request, pauses on unsafe work,
and reuses the tool registry's existing visible-change verification.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import agent.perception as perception
from browser import BrowserResolver, browser_bridge, browser_store
from runtime_state import runtime_state_store
from tools import registry as tool_registry


SENSITIVE_TERMS = {
    "password",
    "passcode",
    "otp",
    "2fa",
    "mfa",
    "credit card",
    "card number",
    "cvv",
    "ssn",
    "social security",
    "bank",
    "wire",
    "delete",
    "remove account",
    "purchase",
    "buy",
    "send money",
    "transfer",
    "submit",
    "confirm",
    "finalize",
}

ACTION_TO_TOOL = {
    "click": "click_element",
    "desktop_click": "click_element",
    "type": "type_text",
    "desktop_type": "type_text",
    "press_key": "press_key",
    "shortcut": "run_shortcut",
    "open_app": "open_app",
    "browser_click": "browser_click_ref",
    "browser_type": "browser_type_ref",
    "browser_select": "browser_select_ref",
}


@dataclass
class ContractEvent:
    trace_id: str
    phase: str
    ok: bool
    status: str
    timestamp: float = field(default_factory=time.time)
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class AdeleLocalActionContract:
    def __init__(self) -> None:
        self._resolver = BrowserResolver()
        self._events: Dict[str, List[ContractEvent]] = {}

    def new_trace_id(self) -> str:
        return f"trace_{uuid.uuid4().hex[:12]}"

    def _trace_id(self, trace_id: str = "") -> str:
        return str(trace_id or "").strip() or self.new_trace_id()

    def _record(
        self,
        trace_id: str,
        phase: str,
        ok: bool,
        status: str,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        event = ContractEvent(
            trace_id=trace_id,
            phase=phase,
            ok=ok,
            status=status,
            message=message,
            details=details or {},
        )
        self._events.setdefault(trace_id, []).append(event)
        return {
            "ok": ok,
            "trace_id": trace_id,
            "phase": phase,
            "status": status,
            "message": message,
            **(details or {}),
        }

    def history(self, trace_id: str = "") -> Dict[str, Any]:
        if trace_id:
            events = self._events.get(trace_id, [])
        else:
            events = [event for trace_events in self._events.values() for event in trace_events]
        events = sorted(events, key=lambda event: event.timestamp)[-80:]
        return {
            "ok": True,
            "trace_id": trace_id,
            "events": [asdict(event) for event in events],
        }

    def _action_mode(self, requested_mode: str = "") -> str:
        mode = (requested_mode or os.environ.get("ADELE_ACTION_MODE") or "guide").strip().lower()
        if mode in {"guide", "assist", "autopilot"}:
            return mode
        return "guide"

    def _permission_state(self) -> Dict[str, Any]:
        state = runtime_state_store.snapshot()
        browser = state.browser_state
        os_state = state.os_state
        microphone = "unknown"
        try:
            import speech_recognition  # noqa: F401

            microphone = "available"
        except Exception:
            microphone = "missing_runtime"
        screen_access = "available" if os_state.active_app or os_state.window_title else "unknown"
        active_window = "available" if os_state.active_app or os_state.window_title else "unknown"
        permissions = {
            "microphone": microphone,
            "screen_capture": screen_access,
            "active_window": active_window,
            "overlay": "available",
            "browser_context": "connected" if browser.connected else "not_connected",
        }
        required_ok = all(
            permissions[name] in {"available", "connected"}
            for name in ("microphone", "screen_capture", "active_window", "overlay")
        )
        return {
            "permissions": permissions,
            "required_complete": required_ok,
            "browser_connected": bool(browser.connected),
        }

    async def observe(self, trace_id: str = "", include_vision: bool = False) -> Dict[str, Any]:
        tid = self._trace_id(trace_id)
        ctx = await perception.snapshot(include_vision=include_vision)
        bridge_state = runtime_state_store.snapshot().browser_state
        permission_state = self._permission_state()
        details = {
            "active_app": ctx.active_app,
            "window_title": ctx.window_title,
            "browser_url": ctx.browser_url,
            "page_title": ctx.page_title,
            "has_visible_text": bool(ctx.visible_text),
            "has_screenshot": bool(ctx.screenshot_path),
            "screenshot_path": ctx.screenshot_path or "",
            "browser": {
                "connected": bool(bridge_state.connected),
                "session_id": bridge_state.session_id,
                "url": bridge_state.url,
                "title": bridge_state.title,
            },
            "action_mode": self._action_mode(),
            **permission_state,
        }
        return self._record(tid, "observe", True, "observed", "Observed current desktop state.", details)

    async def visual_context(
        self,
        trace_id: str = "",
        intent: str = "",
        include_screenshot: bool = True,
    ) -> Dict[str, Any]:
        tid = self._trace_id(trace_id)
        ctx = await perception.snapshot(request_text=intent, include_vision=include_screenshot)
        snapshot = browser_store.get_snapshot()
        browser_candidates = []
        if snapshot:
            browser_candidates = [
                {
                    "ref_id": element.ref_id,
                    "label": element.primary_label(),
                    "role": element.role or element.tag,
                    "bounds": element.bounds,
                    "actions": element.action_types,
                }
                for element in snapshot.elements[:40]
                if element.visible and element.enabled
            ]
        details = {
            "active_app": ctx.active_app,
            "window_title": ctx.window_title,
            "screenshot_path": ctx.screenshot_path or "",
            "browser_url": ctx.browser_url,
            "page_title": ctx.page_title,
            "browser_candidate_count": len(browser_candidates),
            "browser_candidates": browser_candidates,
        }
        return self._record(
            tid,
            "visual_context",
            True,
            "context_ready",
            "Visual context is ready.",
            details,
        )

    async def ground_target(
        self,
        trace_id: str = "",
        query: str = "",
        action: str = "click",
        limit: int = 5,
    ) -> Dict[str, Any]:
        tid = self._trace_id(trace_id)
        query = str(query or "").strip()
        action = str(action or "click").strip().lower()
        if not query:
            return self._record(
                tid,
                "ground_target",
                False,
                "paused",
                "Target query is required.",
                {"pause_reason": "missing_target_query"},
            )

        snapshot = browser_store.get_snapshot()
        if snapshot and browser_bridge.is_connected():
            candidates = self._resolver.describe_candidates(
                query,
                snapshot.elements,
                action="type" if action in {"type", "browser_type"} else action,
                limit=max(1, min(int(limit or 5), 10)),
            )
            if candidates:
                return self._record(
                    tid,
                    "ground_target",
                    True,
                    "grounded",
                    "Grounded target from browser snapshot.",
                    {
                        "target": candidates[0],
                        "candidates": candidates,
                        "source": "browser_bridge",
                        "session_id": snapshot.session_id,
                        "generation": snapshot.generation,
                    },
                )

        # Fallback to CDP coordinate resolver
        cdp_element = await self._resolver.resolve_via_cdp(query, action)
        if cdp_element:
            candidate = {
                "ref_id": cdp_element.ref_id,
                "label": cdp_element.primary_label(),
                "role": cdp_element.role,
                "bounds": cdp_element.bounds,
                "actions": cdp_element.action_types,
                "x": cdp_element.bounds.get("mid_x"),
                "y": cdp_element.bounds.get("mid_y"),
            }
            return self._record(
                tid,
                "ground_target",
                True,
                "grounded",
                "Grounded target from browser via CDP.",
                {
                    "target": candidate,
                    "candidates": [candidate],
                    "source": "cdp",
                    "session_id": "cdp_session",
                    "generation": 1,
                },
            )

        return self._record(
            tid,
            "ground_target",
            False,
            "paused",
            "Adele could not ground that target deterministically.",
            {
                "pause_reason": "target_not_grounded",
                "source": "browser_bridge" if snapshot else "desktop_visual",
                "query": query,
                "action": action,
            },
        )


    def _contains_sensitive_intent(self, payload: Dict[str, Any]) -> bool:
        haystack = " ".join(
            str(payload.get(key, ""))
            for key in ("query", "text", "label", "target", "reason", "action")
        ).lower()
        return any(term in haystack for term in SENSITIVE_TERMS)

    def _coerce_one_action(self, payload: Dict[str, Any]) -> Optional[str]:
        if isinstance(payload.get("actions"), list):
            return "actions_array_not_allowed"
        action = str(payload.get("action") or "").strip().lower()
        if not action:
            return "missing_action"
        if action not in ACTION_TO_TOOL:
            return "unsupported_action"
        return None

    def _tool_args(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        ref_id = str(payload.get("ref_id") or payload.get("target_ref") or "").strip()
        if action == "click" or action == "desktop_click":
            return {
                "x": int(payload.get("x")),
                "y": int(payload.get("y")),
                "click_type": str(payload.get("click_type") or "single"),
            }
        if action in {"type", "desktop_type"}:
            return {"text": str(payload.get("text") or "")}
        if action == "press_key":
            return {
                "key": str(payload.get("key") or ""),
                "times": int(payload.get("times") or 1),
            }
        if action == "shortcut":
            return {"keys": str(payload.get("keys") or payload.get("shortcut") or "")}
        if action == "open_app":
            return {"app_name": str(payload.get("app_name") or payload.get("name") or "")}
        if action == "browser_click":
            return {"ref_id": ref_id, "session_id": str(payload.get("session_id") or "")}
        if action == "browser_type":
            return {
                "ref_id": ref_id,
                "text": str(payload.get("text") or ""),
                "clear_first": bool(payload.get("clear_first", False)),
                "session_id": str(payload.get("session_id") or ""),
            }
        if action == "browser_select":
            return {
                "ref_id": ref_id,
                "option": str(payload.get("option") or ""),
                "session_id": str(payload.get("session_id") or ""),
            }
        return {}

    async def act(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        tid = self._trace_id(str(payload.get("trace_id") or ""))
        problem = self._coerce_one_action(payload)
        if problem:
            return self._record(
                tid,
                "act",
                False,
                "paused",
                "Adele accepts exactly one supported action per request.",
                {"pause_reason": problem},
            )

        action = str(payload.get("action") or "").strip().lower()
        mode = self._action_mode(str(payload.get("mode") or ""))
        confirmed = bool(payload.get("confirmed") or payload.get("user_confirmed"))
        sensitive_confirmed = bool(payload.get("confirmed_sensitive"))

        if self._contains_sensitive_intent(payload) and not sensitive_confirmed:
            return self._record(
                tid,
                "act",
                False,
                "paused",
                "This looks sensitive, so Adele paused before acting.",
                {"pause_reason": "sensitive_action_requires_confirmation", "action_mode": mode},
            )
        if mode == "guide" and not confirmed:
            return self._record(
                tid,
                "act",
                False,
                "paused",
                "Guide Mode explains actions but does not execute until confirmed.",
                {"pause_reason": "guide_mode_requires_confirmation", "action_mode": mode},
            )

        ref_id = str(payload.get("ref_id") or payload.get("target_ref") or "").strip()
        if payload.get("source") == "cdp" or ref_id == "cdp_match":
            # Direct CDP execution!
            from browser.cdp import cdp_client
            query = str(payload.get("query") or payload.get("label") or payload.get("text") or "").strip()
            ok = False
            msg = "CDP action failed."
            details = {"action": action, "query": query, "source": "cdp"}

            if action in {"click", "browser_click"}:
                res = await cdp_client.cdp_click(query)
                if res and res.get("ok"):
                    ok = True
                    msg = res.get("message", "Clicked element via CDP.")
                    details["cdp_result"] = res
            elif action in {"type", "browser_type"}:
                text = str(payload.get("text") or "")
                res = await cdp_client.cdp_type(query, text)
                if res and res.get("ok"):
                    ok = True
                    msg = res.get("message", "Typed into element via CDP.")
                    details["cdp_result"] = res
                    details["text"] = text
            else:
                msg = f"Unsupported CDP action: {action}"

            observe_after = await self.observe(trace_id=tid, include_vision=False)
            details["post_observe"] = observe_after

            return self._record(
                tid,
                "act",
                ok,
                "acted" if ok else "paused",
                msg,
                details,
            )

        tool_name = ACTION_TO_TOOL[action]
        try:
            tool_args = self._tool_args(action, payload)
        except Exception as exc:
            return self._record(
                tid,
                "act",
                False,
                "paused",
                f"Invalid action arguments: {exc}",
                {"pause_reason": "invalid_action_args", "action": action},
            )

        if not any(str(value).strip() for value in tool_args.values() if value is not None):
            return self._record(
                tid,
                "act",
                False,
                "paused",
                "Action arguments are incomplete.",
                {"pause_reason": "missing_action_args", "action": action, "tool": tool_name},
            )

        tool_args["reasoning"] = f"Contract trace {tid}: execute one confirmed {action} action."
        result_text = await tool_registry.execute(tool_name, tool_args)
        ok = True
        parsed: Any = None
        try:
            parsed = json.loads(result_text)
            if isinstance(parsed, dict) and parsed.get("ok") is False:
                ok = False
        except Exception:
            parsed = None

        status = "acted" if ok else "paused"
        pause_reason = ""
        if not ok and isinstance(parsed, dict):
            error = parsed.get("error") if isinstance(parsed.get("error"), dict) else {}
            pause_reason = (
                str(parsed.get("code") or "")
                or str(error.get("code") or "")
                or "tool_reported_failure"
            )
            if pause_reason in {"tool.no_visible_change", "no_visible_change"}:
                status = "paused"

        observe_after = await self.observe(trace_id=tid, include_vision=False)
        details = {
            "action": action,
            "tool": tool_name,
            "tool_args": {k: v for k, v in tool_args.items() if k != "reasoning"},
            "tool_result": parsed if parsed is not None else result_text,
            "post_observe": observe_after,
            "action_mode": mode,
        }
        if pause_reason:
            details["pause_reason"] = pause_reason
        return self._record(
            tid,
            "act",
            ok,
            status,
            "Action executed." if ok else "Action paused or failed validation.",
            details,
        )


_CONTRACT: Optional[AdeleLocalActionContract] = None


def get_local_action_contract() -> AdeleLocalActionContract:
    global _CONTRACT
    if _CONTRACT is None:
        _CONTRACT = AdeleLocalActionContract()
    return _CONTRACT
