"""
ADELE — Providers Package
===============================
Re-exports for convenient importing.
"""

from providers.antigravity import AntigravityProvider, DEFAULT_ANTIGRAVITY_AGENT, is_antigravity_agent
from providers.base import LLMProvider, LLMResponse, ToolCall
from providers.codex_app_server import CodexAppServerProvider
from providers.gemini import GeminiProvider
from providers.openai_compatible import OpenAICompatibleProvider

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "ToolCall",
    "AntigravityProvider",
    "DEFAULT_ANTIGRAVITY_AGENT",
    "CodexAppServerProvider",
    "GeminiProvider",
    "OpenAICompatibleProvider",
    "is_antigravity_agent",
]
