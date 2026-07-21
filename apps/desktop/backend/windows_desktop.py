from __future__ import annotations

import asyncio
import ctypes
import os
import subprocess
import time
import webbrowser
from ctypes import wintypes
from dataclasses import dataclass
from typing import Optional


IS_WINDOWS = os.name == "nt"


@dataclass
class ActiveWindowInfo:
    app_name: str = ""
    window_title: str = ""
    process_id: int = 0
    process_name: str = ""


def _creationflags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run_powershell(command: str, *, input_text: str = "", timeout: float = 4.0) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        input=input_text,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        creationflags=_creationflags(),
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "").strip())
    return (result.stdout or "").strip()


def get_active_window_info_sync() -> ActiveWindowInfo:
    if not IS_WINDOWS:
        return ActiveWindowInfo()

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ActiveWindowInfo()

    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    title = buffer.value or ""

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process_id = int(pid.value or 0)
    process_name = ""
    if process_id:
        try:
            process_name = _run_powershell(
                f"(Get-Process -Id {process_id} -ErrorAction Stop).ProcessName",
                timeout=2.0,
            ).splitlines()[0].strip()
        except Exception:
            process_name = ""

    return ActiveWindowInfo(
        app_name=process_name or title,
        window_title=title,
        process_id=process_id,
        process_name=process_name,
    )


async def get_active_window_info() -> ActiveWindowInfo:
    return await asyncio.to_thread(get_active_window_info_sync)


def _focus_terms(app_name: str) -> tuple[str, ...]:
    target = " ".join((app_name or "").lower().split())
    aliases = {
        "google chrome": ("google chrome", "chrome"),
        "chrome": ("google chrome", "chrome"),
        "microsoft edge": ("microsoft edge", "edge"),
        "edge": ("microsoft edge", "edge"),
        "visual studio code": ("visual studio code", "code"),
        "vs code": ("visual studio code", "code"),
        "file explorer": ("file explorer", "explorer"),
    }
    return aliases.get(target, (target,)) if target else ()


def focus_app_sync(app_name: str) -> bool:
    """Bring a visible application window to the foreground on Windows."""
    if not IS_WINDOWS:
        return False

    terms = _focus_terms(app_name)
    if not terms:
        return False

    try:
        from pywinauto import Desktop

        candidates = []
        for window in Desktop(backend="uia").windows():
            try:
                if not window.is_visible():
                    continue
                title = (window.window_text() or "").lower()
                score = max((100 if term == title else 75 if term in title else 0) for term in terms)
                if score:
                    candidates.append((score, window))
            except Exception:
                continue

        if not candidates:
            return False

        _, target = max(candidates, key=lambda item: item[0])
        try:
            target.set_focus()
        except Exception:
            hwnd = int(target.handle)
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            if not ctypes.windll.user32.SetForegroundWindow(hwnd):
                return False
        time.sleep(0.12)
        active = get_active_window_info_sync()
        observed = f"{active.app_name} {active.window_title}".lower()
        return any(term in observed for term in terms)
    except Exception:
        return False


async def focus_app(app_name: str) -> bool:
    return await asyncio.to_thread(focus_app_sync, app_name)


async def get_clipboard_text() -> Optional[str]:
    if not IS_WINDOWS:
        return None
    try:
        text = await asyncio.to_thread(
            _run_powershell,
            "Get-Clipboard -Raw -Format Text",
            timeout=3.0,
        )
        return text if text else None
    except Exception:
        return None


async def set_clipboard_text(text: str) -> None:
    if not IS_WINDOWS:
        return
    await asyncio.to_thread(
        _run_powershell,
        "Set-Clipboard -Value $input",
        input_text=text,
        timeout=4.0,
    )


def capture_screenshot_sync(filepath: str, region: Optional[tuple[int, int, int, int]] = None) -> tuple[int, int]:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    try:
        from PIL import ImageGrab

        if region:
            x, y, width, height = region
            bbox = (int(x), int(y), int(x + width), int(y + height))
            image = ImageGrab.grab(bbox=bbox, all_screens=True)
        else:
            image = ImageGrab.grab(all_screens=True)
        image.save(filepath)
        return image.size
    except ModuleNotFoundError:
        return _capture_screenshot_dotnet(filepath, region)


def _capture_screenshot_dotnet(filepath: str, region: Optional[tuple[int, int, int, int]] = None) -> tuple[int, int]:
    safe_path = filepath.replace("'", "''")
    if region:
        x, y, width, height = [int(v) for v in region]
        bounds_expr = (
            f"New-Object System.Drawing.Rectangle({x}, {y}, "
            f"{max(1, width)}, {max(1, height)})"
        )
    else:
        bounds_expr = "[System.Windows.Forms.SystemInformation]::VirtualScreen"

    script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = {bounds_expr}
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Left, $bounds.Top, 0, 0, $bounds.Size)
$bitmap.Save('{safe_path}', [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
Write-Output "$($bounds.Width),$($bounds.Height)"
"""
    output = _run_powershell(script, timeout=8.0)
    try:
        width_text, height_text = output.splitlines()[-1].split(",", 1)
        return int(width_text), int(height_text)
    except Exception:
        return (0, 0)


async def capture_screenshot(filepath: str, region: Optional[tuple[int, int, int, int]] = None) -> tuple[int, int]:
    return await asyncio.to_thread(capture_screenshot_sync, filepath, region)


def _keyboard_event(vk: int, key_up: bool = False) -> None:
    flags = 0x0002 if key_up else 0
    ctypes.windll.user32.keybd_event(int(vk), 0, flags, 0)


VK_MAP = {
    "backspace": 0x08,
    "tab": 0x09,
    "return": 0x0D,
    "enter": 0x0D,
    "shift": 0x10,
    "control": 0x11,
    "ctrl": 0x11,
    "alt": 0x12,
    "option": 0x12,
    "pause": 0x13,
    "escape": 0x1B,
    "esc": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "delete": 0x2E,
    "del": 0x2E,
    "win": 0x5B,
    "windows": 0x5B,
    "command": 0x11,
    "cmd": 0x11,
}


def vk_for_key(key: str) -> Optional[int]:
    normalized = (key or "").strip().lower()
    if not normalized:
        return None
    if normalized in VK_MAP:
        return VK_MAP[normalized]
    if len(normalized) == 1:
        char = normalized.upper()
        if "A" <= char <= "Z" or "0" <= char <= "9":
            return ord(char)
    if normalized.startswith("f") and normalized[1:].isdigit():
        number = int(normalized[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    return None


async def press_key(key: str, times: int = 1) -> None:
    vk = vk_for_key(key)
    if vk is None:
        raise ValueError(f"Unsupported key: {key}")
    for _ in range(max(1, min(20, int(times or 1)))):
        _keyboard_event(vk, False)
        await asyncio.sleep(0.03)
        _keyboard_event(vk, True)
        await asyncio.sleep(0.05)


async def run_shortcut(keys: str) -> None:
    parts = [part.strip().lower() for part in (keys or "").replace("-", "+").split("+") if part.strip()]
    if not parts:
        raise ValueError("No shortcut keys provided")

    modifiers = parts[:-1]
    final_key = parts[-1]
    modifier_vks = []
    for modifier in modifiers:
        vk = vk_for_key(modifier)
        if vk is not None:
            modifier_vks.append(vk)
    final_vk = vk_for_key(final_key)
    if final_vk is None:
        raise ValueError(f"Unsupported shortcut key: {final_key}")

    for vk in modifier_vks:
        _keyboard_event(vk, False)
        await asyncio.sleep(0.02)
    _keyboard_event(final_vk, False)
    await asyncio.sleep(0.04)
    _keyboard_event(final_vk, True)
    for vk in reversed(modifier_vks):
        await asyncio.sleep(0.02)
        _keyboard_event(vk, True)


async def paste_text(text: str) -> None:
    await set_clipboard_text(text)
    await run_shortcut("ctrl+v")


def move_mouse(x: int, y: int) -> None:
    ctypes.windll.user32.SetCursorPos(int(x), int(y))


def click_mouse(x: int, y: int, click_type: str = "single") -> None:
    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(x), int(y))
    if click_type == "right":
        down, up, clicks = 0x0008, 0x0010, 1
    else:
        down, up, clicks = 0x0002, 0x0004, 2 if click_type == "double" else 1
    for _ in range(clicks):
        user32.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.04)
        user32.mouse_event(up, 0, 0, 0, 0)
        time.sleep(0.06)


def drag_mouse(x: int, y: int, x2: int, y2: int) -> None:
    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.06)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.SetCursorPos(int(x2), int(y2))
    time.sleep(0.08)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


def scroll(lines: int) -> None:
    ctypes.windll.user32.mouse_event(0x0800, 0, 0, int(lines) * 120, 0)


async def open_app(app_name: str, known_urls: Optional[dict[str, str]] = None) -> str:
    target = (app_name or "").strip()
    if not target:
        return "ERROR: app_name is required."

    url = (known_urls or {}).get(target.lower())
    if url:
        webbrowser.open(url)
        return f"Opened {target} in browser."

    aliases = {
        "chrome": "chrome",
        "google chrome": "chrome",
        "edge": "msedge",
        "microsoft edge": "msedge",
        "firefox": "firefox",
        "notepad": "notepad",
        "calculator": "calc",
        "calc": "calc",
        "file explorer": "explorer",
        "explorer": "explorer",
        "terminal": "wt",
        "windows terminal": "wt",
        "powershell": "powershell",
        "cmd": "cmd",
        "command prompt": "cmd",
        "vs code": "code",
        "visual studio code": "code",
    }
    command = aliases.get(target.lower(), target)

    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_creationflags(),
        )
        await asyncio.sleep(0.8)
        active = await get_active_window_info()
        if target.lower() in (active.app_name or "").lower() or target.lower() in (active.window_title or "").lower():
            return f"Opened {target}; it is now foreground."
        return f"Launched {target}. It may still be starting or may be in the background."
    except Exception as exc:
        return f"ERROR: Could not launch {target}: {str(exc)[:200]}"


async def close_window() -> str:
    await run_shortcut("alt+f4")
    return "Sent Alt+F4 to close the active window."


async def get_ui_tree(app_name: str = "", search_term: str = "") -> str:
    try:
        from pywinauto import Application
    except Exception:
        info = await get_active_window_info()
        return (
            "Windows UI Automation tree requires pywinauto. "
            "Current active window fallback:\n"
            f"- App: {info.app_name or 'Unknown'}\n"
            f"- Process: {info.process_name or 'Unknown'} ({info.process_id})\n"
            f"- Title: {info.window_title or 'Unknown'}\n"
            "Use read_screen for visual grounding, or install pywinauto for structured UI trees."
        )

    info = await get_active_window_info()
    if not info.process_id:
        return "ERROR: No active Windows foreground window found."

    def _dump() -> str:
        app = Application(backend="uia").connect(process=info.process_id, timeout=3)
        win = app.top_window()
        rows: list[str] = []
        needle = (search_term or "").lower()
        for elem in win.descendants()[:250]:
            try:
                rect = elem.rectangle()
                name = elem.window_text() or ""
                control = elem.friendly_class_name() or elem.element_info.control_type or "Element"
                line = f'- [{control}] "{name}" at {rect.left},{rect.top} (size: {rect.width()}x{rect.height()})'
                if not needle or needle in line.lower():
                    rows.append(line)
            except Exception:
                continue
        return "\n".join(rows)

    try:
        output = await asyncio.to_thread(_dump)
        return output[:10000] if output else ("No elements found matching search." if search_term else "Window has no accessible UI elements.")
    except Exception as exc:
        return f"ERROR dumping Windows UI tree: {str(exc)[:200]}"
