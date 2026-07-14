from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from runtime_state import runtime_state_store


UI_MUTATING_TOOLS: frozenset[str] = frozenset({
    "click_ui", "type_in_field", "type_text", "press_key",
    "run_shortcut", "click_element", "hover_element", "mouse_action",
    "browser_click_ref", "browser_type_ref", "browser_select_ref",
    "browser_click_match", "find_and_act", "open_app", "open_url",
})


@dataclass
class ActionVerificationContext:
    tool_name: str
    browser_session_id: str = ""
    browser_generation: int = 0
    screen_hash: str = ""
    screenshot_path: str = ""
    resolver_source: str = "desktop"


@dataclass
class ActionVerificationResult:
    changed: bool
    source: str
    message: str
    details: dict[str, Any]


def _looks_like_browser_tool(tool_name: str) -> bool:
    return str(tool_name or "").startswith("browser_")


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or ""))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _capture_screen_hash() -> tuple[str, str]:
    screenshot_path = await _capture_screenshot()
    if not screenshot_path:
        return "", ""
    try:
        from PIL import Image

        with Image.open(screenshot_path) as img:
            gray = img.convert("L").resize((8, 8))
            pixels = list(gray.getdata())
        if not pixels:
            return "", screenshot_path
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if px >= avg else "0" for px in pixels)
        return f"{int(bits, 2):016x}", screenshot_path
    except Exception:
        return "", screenshot_path


def _screenshot_capture_dir() -> str:
    try:
        from runtime_paths import ensure_adele_data_layout, get_screenshots_dir

        ensure_adele_data_layout()
        return get_screenshots_dir()
    except Exception:
        return os.path.join(tempfile.gettempdir(), "adele")


async def _capture_screenshot() -> str:
    shot_dir = _screenshot_capture_dir()
    os.makedirs(shot_dir, exist_ok=True)
    filepath = os.path.join(shot_dir, f"verify_{int(time.time() * 1000)}.png")
    try:
        if os.name == "nt":
            from PIL import ImageGrab

            img = await asyncio.to_thread(lambda: ImageGrab.grab(all_screens=True).convert("RGB"))
            await asyncio.to_thread(img.save, filepath, "PNG")
            return filepath if os.path.exists(filepath) else ""

        proc = await asyncio.create_subprocess_exec(
            "screencapture", "-x", "-t", "png", filepath,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=5.0)
        return filepath if os.path.exists(filepath) else ""
    except Exception:
        return ""


def _hamming_distance(left: str, right: str) -> int:
    if not left or not right:
        return 0
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except Exception:
        return 0


async def capture_pre_action_context(tool_name: str) -> ActionVerificationContext:
    ctx = ActionVerificationContext(tool_name=str(tool_name or ""))
    browser_state = runtime_state_store.snapshot().browser_state
    if browser_state.connected and browser_state.session_id:
        ctx.browser_session_id = browser_state.session_id
        ctx.browser_generation = int(browser_state.generation or 0)
    if _looks_like_browser_tool(tool_name):
        ctx.resolver_source = "browser_dom"
        return ctx
    ctx.screen_hash, ctx.screenshot_path = await _capture_screen_hash()
    if ctx.browser_session_id:
        ctx.resolver_source = "windows_uia"
    return ctx


async def verify_post_action_change(
    tool_name: str,
    result_text: str,
    context: ActionVerificationContext,
    settle_delay: float = 0.55,
) -> ActionVerificationResult:
    payload = _json_dict(result_text)
    if payload.get("ok") is False:
        return ActionVerificationResult(
            changed=False,
            source=context.resolver_source,
            message=str(payload.get("message") or payload.get("error_code") or "Action failed."),
            details={"result": payload},
        )

    if _looks_like_browser_tool(tool_name):
        verification = payload.get("verification", {}) if isinstance(payload.get("verification"), dict) else {}
        pre_gen = int(payload.get("pre_generation", context.browser_generation) or 0)
        post_gen = int(payload.get("post_generation", pre_gen) or pre_gen)
        from browser.bridge import browser_bridge
        dom_event = browser_bridge.latest_dom_change(str(payload.get("action_id", "") or ""))
        dom_changed = bool(dom_event and getattr(dom_event, "change_types", None))
        checks = list(verification.get("checks_passed", []) or [])
        if post_gen > pre_gen or dom_changed:
            return ActionVerificationResult(
                changed=True,
                source="browser_dom",
                message="Browser DOM changed after the action.",
                details={
                    "pre_generation": pre_gen,
                    "post_generation": post_gen,
                    "dom_change_types": list(getattr(dom_event, "change_types", []) or []),
                    "checks_passed": checks,
                },
            )
        return ActionVerificationResult(
            changed=False,
            source="browser_dom",
            message="Browser action completed, but the page snapshot did not change.",
            details={
                "pre_generation": pre_gen,
                "post_generation": post_gen,
                "checks_passed": checks,
                "verification": verification,
            },
        )

    if settle_delay > 0:
        await asyncio.sleep(settle_delay)
    after_hash, screenshot_path = await _capture_screen_hash()
    hamming = _hamming_distance(context.screen_hash, after_hash)
    changed = bool(context.screen_hash and after_hash and hamming >= 6)
    if changed:
        return ActionVerificationResult(
            changed=True,
            source="screenshot_hash",
            message="The screen changed after the action.",
            details={
                "before_hash": context.screen_hash,
                "after_hash": after_hash,
                "hamming": hamming,
                "screenshot_path": screenshot_path,
            },
        )
    return ActionVerificationResult(
        changed=False,
        source="screenshot_hash",
        message="The screen looks unchanged after the action.",
        details={
            "before_hash": context.screen_hash,
            "after_hash": after_hash,
            "hamming": hamming,
            "screenshot_path": screenshot_path,
        },
    )


async def with_timeout_retry(
    label: str,
    operation: Callable[[], Awaitable[Any]],
    *,
    timeout_s: float,
    attempts: int = 2,
    retry_on: Optional[Callable[[BaseException], bool]] = None,
    base_delay_s: float = 0.2,
) -> Any:
    last_error: Optional[BaseException] = None
    max_attempts = max(1, int(attempts or 1))
    for attempt in range(1, max_attempts + 1):
        try:
            return await asyncio.wait_for(operation(), timeout=max(0.05, float(timeout_s)))
        except BaseException as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            last_error = exc
            should_retry = attempt < max_attempts and (
                retry_on(exc) if retry_on is not None else isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError))
            )
            if not should_retry:
                raise
            await asyncio.sleep(base_delay_s * attempt)
    if last_error:
        raise last_error
    raise RuntimeError(f"{label} failed without an exception")


def should_retry_tool(tool_name: str) -> bool:
    return str(tool_name or "") not in UI_MUTATING_TOOLS
