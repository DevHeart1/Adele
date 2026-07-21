"""Regression coverage for the ChatGPT-only desktop screen harness."""

import os
import sys

import pytest
from PIL import Image


BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from agent import perception
from agent.core_v2 import AdeleAgentV2
from agent.planner import ExecutionStep
from agent.vision_harness import analyze_screen, use_vision_provider
from agent.verifier import VerificationResult
from agent.world_state import WorldState
from providers.base import LLMResponse
from tools.mac_tools import _fast_visual_locate, read_screen


class FakeVisionProvider:
    supports_vision = True

    def __init__(self, response: LLMResponse):
        self.response = response
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


@pytest.mark.asyncio
async def test_screen_harness_uses_active_provider_and_deletes_capture(tmp_path, monkeypatch):
    capture = tmp_path / "capture.png"
    Image.new("RGB", (3, 3), color="white").save(capture, "PNG")
    monkeypatch.setattr(perception, "capture_screenshot", lambda: _return(str(capture)))
    monkeypatch.setattr(perception, "_screenshot_capture_dir", lambda: str(tmp_path))
    provider = FakeVisionProvider(LLMResponse(text="Notepad is visible with a Save button."))

    result = await analyze_screen("What is visible?", provider=provider)

    assert result == "Notepad is visible with a Save button."
    assert not capture.exists()
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call["image_data"]
    assert call["tools"] == []
    assert call["thinking_level"] == "low"
    assert call["enable_builtin_tools"] is False


@pytest.mark.asyncio
async def test_screen_harness_hides_provider_errors_and_deletes_capture(tmp_path, monkeypatch):
    capture = tmp_path / "private-capture.png"
    Image.new("RGB", (3, 3), color="white").save(capture, "PNG")
    monkeypatch.setattr(perception, "capture_screenshot", lambda: _return(str(capture)))
    monkeypatch.setattr(perception, "_screenshot_capture_dir", lambda: str(tmp_path))
    provider = FakeVisionProvider(LLMResponse(error=r"C:\\Users\\Example\\private-capture.png"))

    result = await analyze_screen("Read the error", provider=provider)

    assert result == "I couldn't read enough visible detail from the screen. Please try again."
    assert "private-capture" not in result
    assert not capture.exists()


@pytest.mark.asyncio
async def test_read_screen_tool_uses_bound_chatgpt_provider(tmp_path, monkeypatch):
    capture = tmp_path / "capture.png"
    Image.new("RGB", (3, 3), color="white").save(capture, "PNG")
    monkeypatch.setattr(perception, "capture_screenshot", lambda: _return(str(capture)))
    monkeypatch.setattr(perception, "_screenshot_capture_dir", lambda: str(tmp_path))
    provider = FakeVisionProvider(LLMResponse(text="Chrome is visible."))

    with use_vision_provider(provider):
        result = await read_screen("Which app is visible?")

    assert result == "Chrome is visible."
    assert len(provider.calls) == 1
    assert not capture.exists()


@pytest.mark.asyncio
async def test_visual_locator_reuses_bound_chatgpt_provider(tmp_path, monkeypatch):
    capture = tmp_path / "capture.png"
    Image.new("RGB", (3, 3), color="white").save(capture, "PNG")
    monkeypatch.setattr(perception, "capture_screenshot", lambda: _return(str(capture)))
    monkeypatch.setattr(perception, "_screenshot_capture_dir", lambda: str(tmp_path))
    provider = FakeVisionProvider(LLMResponse(text="(123, 456)"))

    with use_vision_provider(provider):
        result = await _fast_visual_locate("the Save button")

    assert result == (123, 456)
    assert len(provider.calls) == 1
    assert not capture.exists()


@pytest.mark.asyncio
async def test_screen_result_is_redacted_from_agent_diagnostics(tmp_path, monkeypatch, capsys):
    capture = tmp_path / "capture.png"
    Image.new("RGB", (3, 3), color="white").save(capture, "PNG")
    monkeypatch.setattr(perception, "capture_screenshot", lambda: _return(str(capture)))
    monkeypatch.setattr(perception, "_screenshot_capture_dir", lambda: str(tmp_path))
    provider = FakeVisionProvider(LLMResponse(text="Visible secret screen text."))
    agent = AdeleAgentV2(persist=False)

    async def verified(**_kwargs):
        return VerificationResult(True, 1.0, "Screen described")

    monkeypatch.setattr(agent.verifier, "verify_with_visual", verified)
    step = ExecutionStep(
        id=1,
        description="Describe the visible screen",
        tool="read_screen",
        args={"question": "What is visible?"},
    )

    with use_vision_provider(provider):
        assert await agent._execute_step(step, WorldState(active_app="Notepad"), ws_callback=None)

    output = capsys.readouterr().out
    assert "[screen analysis redacted]" in output
    assert "Visible secret screen text." not in output
    assert not capture.exists()


async def _return(value):
    return value
