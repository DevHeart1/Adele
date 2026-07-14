"""Model discovery and strict Build Week model selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


class CodexModelUnavailable(Exception):
    """GPT-5.6 was not advertised by the authenticated App Server session."""


@dataclass(frozen=True)
class CodexModel:
    id: str
    model: str
    display_name: str
    reasoning_efforts: tuple[str, ...]
    default_reasoning_effort: str
    supports_images: bool


def _as_model(value: dict[str, Any]) -> CodexModel:
    efforts = tuple(
        str(item.get("reasoningEffort"))
        for item in value.get("supportedReasoningEfforts", [])
        if isinstance(item, dict) and item.get("reasoningEffort")
    )
    modalities = {str(item).lower() for item in value.get("inputModalities", ["text"])}
    return CodexModel(
        id=str(value.get("id") or value.get("model") or ""),
        model=str(value.get("model") or value.get("id") or ""),
        display_name=str(value.get("displayName") or value.get("model") or "GPT-5.6"),
        reasoning_efforts=efforts,
        default_reasoning_effort=str(value.get("defaultReasoningEffort") or "medium"),
        supports_images="image" in modalities,
    )


def select_build_week_model(models: Iterable[dict[str, Any]]) -> CodexModel:
    """Choose only GPT-5.6, allowing the documented Sol variant as a strict fallback."""
    parsed = [_as_model(item) for item in models if isinstance(item, dict)]
    exact = next((item for item in parsed if item.model.lower() == "gpt-5.6" or item.id.lower() == "gpt-5.6"), None)
    sol = next((item for item in parsed if item.model.lower() == "gpt-5.6-sol" or item.id.lower() == "gpt-5.6-sol"), None)
    selected = exact or sol
    if not selected:
        raise CodexModelUnavailable("GPT-5.6 is not available for this ChatGPT account.")
    return selected
