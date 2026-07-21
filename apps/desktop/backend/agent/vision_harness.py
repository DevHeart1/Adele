"""Consent-bound screen analysis through Adele's active ChatGPT provider."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

from providers import LLMProvider

import agent.perception as perception


_active_provider: ContextVar[Optional[LLMProvider]] = ContextVar(
    "adele_active_vision_provider",
    default=None,
)

_CAPTURE_TIMEOUT_SECONDS = 8.0
_ANALYSIS_TIMEOUT_SECONDS = 60.0

_VISION_SYSTEM_PROMPT = """You are ADELE's desktop screen observer.
Answer only from visible evidence in the supplied screenshot. Do not invent
details, reveal hidden reasoning, include internal plans, or take actions.
For a general question, concisely describe the active application, visible text,
and important controls. If asked to locate a visible clickable target, provide
one coordinate in the exact form `(x, y)` only when you can see it clearly;
otherwise state that it is not visible."""


@contextmanager
def use_vision_provider(provider: LLMProvider) -> Iterator[None]:
    """Bind the already-selected provider for one agent execution.

    This preserves the single shared Codex App Server provider and avoids any
    secondary API client, credentials, or browser session.
    """
    token = _active_provider.set(provider)
    try:
        yield
    finally:
        _active_provider.reset(token)


async def analyze_screen(question: str = "", provider: Optional[LLMProvider] = None) -> str:
    """Capture a temporary screenshot and analyze it with the active GPT-5.6 path."""
    selected_provider = provider or _active_provider.get()
    if selected_provider is None:
        return "Screen analysis is unavailable until ChatGPT is ready."
    if not bool(getattr(selected_provider, "supports_vision", False)):
        return "Screen analysis is not available with the selected ChatGPT model."

    screenshot_path: Optional[str] = None
    try:
        try:
            screenshot_path = await asyncio.wait_for(
                perception.capture_screenshot(),
                timeout=_CAPTURE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return "I couldn't capture the screen in time. Please try again."

        if not screenshot_path:
            return "I couldn't capture the screen. Check that Adele is running in your desktop session and try again."

        try:
            with open(screenshot_path, "rb") as image_file:
                image_data = image_file.read()
        except OSError:
            return "I couldn't read the temporary screen capture. Please try again."

        if not image_data:
            return "I couldn't capture any screen content. Please try again."

        prompt = (question or "What is visible on the screen?").strip()[:800]
        try:
            response = await asyncio.wait_for(
                selected_provider.generate(
                    messages=[{"role": "user", "parts": [{"text": prompt}]}],
                    system_prompt=_VISION_SYSTEM_PROMPT,
                    tools=[],
                    image_data=image_data,
                    thinking_level="low",
                    enable_builtin_tools=False,
                ),
                timeout=_ANALYSIS_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return "I couldn't analyze the screen in time. Please try again."
        except Exception:
            return "I couldn't analyze the screen with ChatGPT. Please try again."

        text = str(getattr(response, "text", "") or "").strip()
        if text:
            return text[:4000]
        return "I couldn't read enough visible detail from the screen. Please try again."
    finally:
        perception.delete_temporary_screenshot(screenshot_path)
