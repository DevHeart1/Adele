"""Tests for Antigravity Interactions provider helpers."""

import os
import sys

backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, backend_path)

from providers.antigravity import (
    DEFAULT_ANTIGRAVITY_AGENT,
    AntigravityProvider,
    _adele_tools_to_interactions,
    _messages_to_input,
    _parse_interaction,
    is_antigravity_agent,
)
from adk_agent.config import adk_planner_model


class _FakeContent:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _FakeModelOutputStep:
    def __init__(self, text: str):
        self.type = "model_output"
        self.content = [_FakeContent(text)]


class _FakeFunctionCallStep:
    def __init__(self, name: str, arguments: dict):
        self.type = "function_call"
        self.name = name
        self.arguments = arguments


class _FakeInteraction:
    def __init__(self, steps, status="completed", error=None):
        self.steps = steps
        self.status = status
        self.error = error
        self.id = "interaction-test"


def test_default_agent_constant():
    assert DEFAULT_ANTIGRAVITY_AGENT == "antigravity-preview-05-2026"


def test_antigravity_provider_exposes_model_alias_for_router():
    provider = AntigravityProvider(api_key="", agent="antigravity-preview-05-2026")
    assert provider._model == "antigravity-preview-05-2026"


def test_is_antigravity_agent():
    assert is_antigravity_agent("antigravity-preview-05-2026")
    assert not is_antigravity_agent("gemini-3-flash-preview")


def test_messages_to_input_simple_text():
    messages = [{"role": "user", "parts": [{"text": "Hello ADELE"}]}]
    assert _messages_to_input(messages) == "Hello ADELE"


def test_adele_tools_include_builtins():
    tools = _adele_tools_to_interactions(
        [{"name": "open_app", "description": "Open an app", "parameters": {"type": "object"}}]
    )
    types = {tool["type"] for tool in tools}
    assert "code_execution" in types
    assert "google_search" in types
    assert "url_context" in types
    assert any(tool.get("name") == "open_app" for tool in tools)


def test_parse_interaction_text_and_tool_calls():
    interaction = _FakeInteraction(
        [
            _FakeModelOutputStep("On it."),
            _FakeFunctionCallStep("open_app", {"app_name": "Spotify"}),
        ]
    )
    parsed = _parse_interaction(interaction)
    assert parsed.text == "On it."
    assert len(parsed.tool_calls) == 1
    assert parsed.tool_calls[0].name == "open_app"


def test_adk_planner_ignores_antigravity_fast_model(monkeypatch):
    monkeypatch.delenv("ADELE_ADK_PLANNER_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_FAST_MODEL", "antigravity-preview-05-2026")
    assert adk_planner_model() == "gemini-3-flash-preview"
