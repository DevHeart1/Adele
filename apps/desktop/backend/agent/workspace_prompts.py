"""
Optional user-authored markdown at the data root (OpenClaw-style workspace files).

Reads, when present:
  ADELE.md — primary user instructions / product notes
  SOUL.md     — stable identity, tone, boundaries
  AGENTS.md   — how the assistant should behave
  TOOLS.md    — extra tool usage notes (does not replace the real tool registry)

Disable entirely: ADELE_DISABLE_WORKSPACE_MD=1
"""

from __future__ import annotations

import os
from functools import partial
from typing import Optional

from runtime_paths import get_adele_data_root

print = partial(print, flush=True)

# Order: general → identity → behavior → tool hints
_WORKSPACE_FILES = (
    "ADELE.md",
    "SOUL.md",
    "AGENTS.md",
    "TOOLS.md",
)

_MAX_PER_FILE = 48 * 1024
_MAX_TOTAL = 96 * 1024

_cache_key: Optional[tuple[tuple[str, float], ...]] = None
_cache_text: str = ""


def _disabled() -> bool:
    v = (os.environ.get("ADELE_DISABLE_WORKSPACE_MD") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _snapshot_mtimes() -> tuple[tuple[str, float], ...]:
    root = get_adele_data_root()
    out: list[tuple[str, float]] = []
    for name in _WORKSPACE_FILES:
        path = os.path.join(root, name)
        if os.path.isfile(path):
            try:
                out.append((path, os.path.getmtime(path)))
            except OSError:
                out.append((path, 0.0))
    return tuple(out)


def load_workspace_prompt_bundle() -> str:
    """
    Return formatted markdown blocks for any workspace files that exist.
    Empty string if none or disabled.
    """
    global _cache_key, _cache_text

    if _disabled():
        return ""

    key = _snapshot_mtimes()
    if key == _cache_key:
        return _cache_text

    if not key:
        _cache_key = key
        _cache_text = ""
        return ""

    parts: list[str] = []
    total = 0
    root = get_adele_data_root()

    for name in _WORKSPACE_FILES:
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                raw = f.read(_MAX_PER_FILE + 1)
        except OSError as e:
            print(f"[WorkspacePrompts] ⚠ Could not read {name}: {e}")
            continue

        truncated = False
        if len(raw) > _MAX_PER_FILE:
            raw = raw[:_MAX_PER_FILE]
            truncated = True

        block = raw.strip()
        if not block:
            continue
        if truncated:
            block += "\n…[truncated by ADELE workspace file size limit]"

        header = f"### From `{name}` (user workspace)\n"
        segment = header + block
        if total + len(segment) > _MAX_TOTAL:
            segment = segment[: _MAX_TOTAL - total].rstrip()
            segment += "\n…[total workspace prompt cap reached]"
            parts.append(segment)
            break
        parts.append(segment)
        total += len(segment)

    combined = "\n\n".join(parts).strip()
    if combined:
        print(f"[WorkspacePrompts] Injected {len(key)} workspace file(s), ~{total} chars")

    _cache_key = key
    _cache_text = combined
    return _cache_text


def format_for_system_prompt(bundle: str) -> str:
    if not bundle.strip():
        return ""
    return (
        "\n\n=== User workspace (markdown) ===\n"
        "The following is written by the user on disk. Treat it as authoritative "
        "for tone, boundaries, and preferences where it does not conflict with safety rules.\n\n"
        f"{bundle}\n"
        "=== End user workspace ==="
    )
