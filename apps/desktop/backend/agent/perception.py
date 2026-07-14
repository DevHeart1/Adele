"""
ADELE - platform-aware perception engine.

L1: Native desktop metadata -> active app, window title, clipboard.
L2: Browser Bridge DOM -> page URL/title/text/selection when available.
L3: Screenshot capture -> visual understanding on demand.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from runtime_state import runtime_state_store


IS_WINDOWS = sys.platform.startswith("win")


@dataclass
class ContextSnapshot:
    """Combined context from all perception layers."""

    active_app: str = ""
    window_title: str = ""
    browser_url: Optional[str] = None
    page_title: Optional[str] = None
    selected_text: Optional[str] = None
    visible_text: Optional[str] = None
    screenshot_path: Optional[str] = None
    clipboard: Optional[str] = None
    timestamp: float = 0.0

    def to_prompt_string(self) -> str:
        now = datetime.now()
        lines = [
            "[Desktop Context]",
            f"  Date: {now.strftime('%A, %B %d, %Y')}",
            f"  Time: {now.strftime('%I:%M %p')}",
            f"  Active App: {self.active_app or 'Unknown'}",
            f"  Window Title: {self.window_title or 'Unknown'}",
        ]
        if self.browser_url:
            lines.append(f"  Browser URL: {self.browser_url}")
        if self.page_title and self.page_title != self.window_title:
            lines.append(f"  Page Title: {self.page_title}")
        if self.selected_text:
            lines.append(f"  Selected Text: {self.selected_text[:500]}")
        if self.visible_text:
            trimmed = self.visible_text[:1000].strip()
            if trimmed:
                lines.append(f"  Visible Page Text (first 1000 chars): {trimmed}")
        if self.clipboard:
            lines.append(f"  Clipboard: {self.clipboard[:300]}")
        if self.screenshot_path:
            lines.append("  Screenshot: attached (use read_screen for full analysis)")
        lines.append("[End Context]")
        return "\n".join(lines)


BROWSERS = {
    "chrome",
    "google chrome",
    "safari",
    "arc",
    "firefox",
    "brave browser",
    "brave",
    "microsoft edge",
    "msedge",
    "chromium",
}


async def _run_osascript(script: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript",
            "-e",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
        return stdout.decode("utf-8", errors="replace").strip()
    except (asyncio.TimeoutError, Exception):
        return ""


async def get_active_app() -> str:
    if IS_WINDOWS:
        from windows_desktop import get_active_window_info

        info = await get_active_window_info()
        return info.app_name or info.process_name or ""
    return await _run_osascript(
        'tell application "System Events" to get name of first process whose frontmost is true'
    )


async def get_window_title() -> str:
    if IS_WINDOWS:
        from windows_desktop import get_active_window_info

        info = await get_active_window_info()
        return info.window_title or ""
    return await _run_osascript(
        'tell application "System Events" to get title of front window of (first process whose frontmost is true)'
    )


async def get_browser_url(app_name: str) -> Optional[str]:
    bridge_state = runtime_state_store.snapshot().browser_state
    if bridge_state.connected and bridge_state.url:
        return bridge_state.url

    if IS_WINDOWS:
        return None

    name_lower = app_name.lower()
    if "chrome" in name_lower or "chromium" in name_lower or "brave" in name_lower:
        return await _run_osascript(
            f'tell application "{app_name}" to get URL of active tab of front window'
        )
    if "safari" in name_lower:
        return await _run_osascript('tell application "Safari" to get URL of front document')
    if "arc" in name_lower:
        return await _run_osascript(
            'tell application "Arc" to get URL of active tab of front window'
        )
    return None


async def get_clipboard() -> Optional[str]:
    if IS_WINDOWS:
        from windows_desktop import get_clipboard_text

        return await get_clipboard_text()
    try:
        proc = await asyncio.create_subprocess_exec(
            "pbpaste",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
        text = stdout.decode("utf-8", errors="replace").strip()
        return text if text else None
    except Exception:
        return None


def _bridge_attr(name: str) -> Optional[str]:
    bridge_state = runtime_state_store.snapshot().browser_state
    value = getattr(bridge_state, name, None)
    return value if isinstance(value, str) and value else None


async def get_browser_selected_text(app_name: str) -> Optional[str]:
    selected = _bridge_attr("selected_text")
    if selected or IS_WINDOWS:
        return selected

    name_lower = app_name.lower()
    if "chrome" in name_lower or "chromium" in name_lower or "brave" in name_lower:
        return await _run_osascript(
            f'tell application "{app_name}" to execute active tab of front window javascript "window.getSelection().toString()"'
        )
    if "safari" in name_lower:
        return await _run_osascript(
            'tell application "Safari" to do JavaScript "window.getSelection().toString()" in front document'
        )
    return None


async def get_browser_page_content(app_name: str) -> Optional[str]:
    visible_text = _bridge_attr("visible_text") or _bridge_attr("text")
    if visible_text or IS_WINDOWS:
        return visible_text

    name_lower = app_name.lower()
    js = "document.body.innerText.substring(0, 2000)"
    if "chrome" in name_lower or "chromium" in name_lower or "brave" in name_lower:
        return await _run_osascript(
            f'tell application "{app_name}" to execute active tab of front window javascript "{js}"'
        )
    if "safari" in name_lower:
        return await _run_osascript(
            f'tell application "Safari" to do JavaScript "{js}" in front document'
        )
    return None


SCREENSHOT_DIR_LEGACY = os.path.join(tempfile.gettempdir(), "adele")


def _screenshot_capture_dir() -> str:
    try:
        from runtime_paths import ensure_adele_data_layout, get_screenshots_dir

        ensure_adele_data_layout()
        return get_screenshots_dir()
    except Exception:
        return SCREENSHOT_DIR_LEGACY


async def capture_screenshot() -> Optional[str]:
    shot_dir = _screenshot_capture_dir()
    os.makedirs(shot_dir, exist_ok=True)
    filepath = os.path.join(shot_dir, f"screen_{int(time.time())}.png")

    if IS_WINDOWS:
        try:
            from windows_desktop import capture_screenshot as capture_windows_screenshot

            await capture_windows_screenshot(filepath)
            return filepath if os.path.exists(filepath) else None
        except Exception:
            return None

    try:
        proc = await asyncio.create_subprocess_exec(
            "screencapture",
            "-x",
            "-t",
            "png",
            filepath,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if os.path.exists(filepath):
            return filepath
    except Exception:
        pass
    return None


VISION_KEYWORDS = {
    "see",
    "screen",
    "look",
    "show",
    "what's on",
    "what is on",
    "help me with this",
    "this page",
    "what am i",
    "read this",
    "screenshot",
    "image",
    "picture",
    "visual",
}


def _needs_vision(request_text: str) -> bool:
    lower = (request_text or "").lower()
    return any(keyword in lower for keyword in VISION_KEYWORDS)


async def snapshot(request_text: str = "", include_vision: bool = False) -> ContextSnapshot:
    ctx = ContextSnapshot(timestamp=time.time())

    app_name, window_title, clipboard = await asyncio.gather(
        get_active_app(),
        get_window_title(),
        get_clipboard(),
    )
    ctx.active_app = app_name
    ctx.window_title = window_title
    ctx.clipboard = clipboard
    runtime_state_store.update_os_state(
        active_app=app_name,
        window_title=window_title,
        clipboard=clipboard or "",
    )

    bridge_state = runtime_state_store.snapshot().browser_state
    if app_name.lower() in BROWSERS or bridge_state.connected:
        url, selected, page_content = await asyncio.gather(
            get_browser_url(app_name),
            get_browser_selected_text(app_name),
            get_browser_page_content(app_name),
        )
        ctx.browser_url = url
        ctx.selected_text = selected if selected else None
        ctx.visible_text = page_content if page_content else None
        ctx.page_title = bridge_state.title or window_title
        runtime_state_store.update_os_state(
            browser_url=url or "",
            provenance="browser_bridge" if bridge_state.connected else "native_browser_fallback",
            degraded=not bridge_state.connected,
        )

    if include_vision or _needs_vision(request_text):
        ctx.screenshot_path = await capture_screenshot()

    return ctx


async def get_minimal_context() -> str:
    try:
        app_name, window_title = await asyncio.gather(
            get_active_app(),
            get_window_title(),
        )
        return f"Current Desktop State -> Active App: '{app_name}', Window Title: '{window_title}'"
    except Exception:
        return ""


async def build_world_state(user_text: str = "", include_vision: bool = False):
    from agent.world_state import EntityExtractor, IntentParser, WorldState

    ctx = await snapshot(user_text, include_vision)
    intent_parser = IntentParser()
    entity_extractor = EntityExtractor()
    intent = intent_parser.parse(user_text) if user_text else None
    entities = entity_extractor.extract(user_text) if user_text else {}

    return WorldState(
        active_app=ctx.active_app,
        window_title=ctx.window_title,
        browser_url=ctx.browser_url,
        mentioned_apps=entities.get("apps", []),
        mentioned_files=entities.get("files", []),
        mentioned_urls=entities.get("urls", []),
        clipboard_content=ctx.clipboard,
        has_screenshot=ctx.screenshot_path is not None,
        screenshot_path=ctx.screenshot_path,
        intent=intent,
        timestamp=ctx.timestamp,
    )
