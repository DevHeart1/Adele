"""Tests for Gemini 3 provider helpers."""

import os
import sys

backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, backend_path)

from providers.gemini import (
    DEFAULT_GEMINI_MODEL,
    GeminiProvider,
    _resolve_thinking_level,
)


def test_default_model_constant():
    assert DEFAULT_GEMINI_MODEL == "gemini-3-flash-preview"


def test_resolve_thinking_level_explicit():
    assert _resolve_thinking_level("high", temperature=0.7, response_json_schema=None) == "HIGH"
    assert _resolve_thinking_level("minimal", temperature=0.7, response_json_schema=None) == "MINIMAL"


def test_resolve_thinking_level_structured_output_defaults_high():
    assert _resolve_thinking_level(None, temperature=0.15, response_json_schema={"type": "object"}) == "HIGH"


def test_resolve_thinking_level_routing_defaults_low():
    assert _resolve_thinking_level(None, temperature=0.0, response_json_schema=None) == "LOW"


def test_gemini_provider_model_property():
    provider = GeminiProvider(api_key="", model=DEFAULT_GEMINI_MODEL)
    assert provider._model == DEFAULT_GEMINI_MODEL
    assert provider.name == f"gemini ({DEFAULT_GEMINI_MODEL})"
