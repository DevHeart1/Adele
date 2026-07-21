"""
ADELE — local data directories
===================================
Single root for file-backed memory, screenshots, and plan/milestone traces.

Electron sets ADELE_DATA_DIR to app.getPath('userData')/adele-data.
CLI / tests default to ~/.adele when unset.
"""

from __future__ import annotations

import os

_ENV_KEY = "ADELE_DATA_DIR"


def get_adele_data_root() -> str:
    raw = (os.environ.get(_ENV_KEY) or "").strip()
    if raw:
        return os.path.abspath(os.path.expanduser(raw))
    return os.path.expanduser(os.path.join("~", ".adele"))


def get_screenshots_dir() -> str:
    return os.path.join(get_adele_data_root(), "screenshots")


def get_plans_dir() -> str:
    return os.path.join(get_adele_data_root(), "plans")


def get_milestones_dir() -> str:
    return os.path.join(get_adele_data_root(), "milestones")


def get_memories_dir() -> str:
    """Explicit bucket for exports / long-form notes (sessions & vault live under root too)."""
    return os.path.join(get_adele_data_root(), "memories")


def get_conversations_dir() -> str:
    """Optional mirror / exports alongside agent session JSON in sessions/."""
    return os.path.join(get_adele_data_root(), "conversations")


def get_traces_dir() -> str:
    """Local, privacy-safe execution diagnostics (never prompts or screenshots)."""
    return os.path.join(get_adele_data_root(), "traces")


def ensure_adele_data_layout() -> str:
    """
    Create the standard layout under the data root.
    Returns the absolute root path.
    """
    root = get_adele_data_root()
    subs = (
        "sessions",
        "vault",
        "screenshots",
        "plans",
        "milestones",
        "memories",
        "conversations",
        "traces",
    )
    for name in subs:
        os.makedirs(os.path.join(root, name), exist_ok=True)
    return root
