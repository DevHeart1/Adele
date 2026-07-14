"""
ADELE — ADK integration configuration.

Planner uses Google ADK (Agent Development Kit) when enabled and dependencies
are available. Disable with ADELE_USE_ADK_PLANNER=0.
"""

from __future__ import annotations

import os


def adk_planner_enabled() -> bool:
    """Return True when the ADK milestone planner should be used."""
    flag = os.environ.get("ADELE_USE_ADK_PLANNER", "1").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return False
    api_key = (
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GOOGLE_API_KEY", "").strip()
    )
    if api_key:
        return True
    # Vertex / ADC path for Agent Runtime deployments
    if os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip():
        return True
    return False


# Gemini 3 Flash Preview — https://ai.google.dev/gemini-api/docs/models/gemini-3-flash-preview
_DEFAULT_ADK_MODEL = "gemini-3-flash-preview"


def _resolve_adk_model(env_key: str) -> str:
    explicit = os.environ.get(env_key, "").strip()
    if explicit:
        return explicit
    inherited = (
        os.environ.get("GEMINI_FAST_MODEL", "").strip()
        or os.environ.get("GEMINI_MODEL", "").strip()
    )
    if inherited and "antigravity" not in inherited.lower():
        return inherited
    return _DEFAULT_ADK_MODEL


def adk_planner_model() -> str:
    return _resolve_adk_model("ADELE_ADK_PLANNER_MODEL")


def adk_action_model() -> str:
    return _resolve_adk_model("ADELE_ADK_ACTION_MODEL")
