"""Regression tests for temporary visual input cleanup and redaction."""

import asyncio
import os
import sys

import pytest
from PIL import Image


BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from agent import perception
from agent.core_v2 import AdeleAgentV2
from agent.verifier import ToolVerifier, VerificationResult
from reliability import _capture_screen_hash
import reliability


def _image(path):
    Image.new("RGB", (2, 2), color="white").save(path, "PNG")


def test_delete_temporary_screenshot_is_limited_to_adele_directory(tmp_path, monkeypatch):
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    capture = capture_dir / "capture.png"
    outside = tmp_path / "outside.png"
    _image(capture)
    _image(outside)
    monkeypatch.setattr(perception, "_screenshot_capture_dir", lambda: str(capture_dir))

    perception.delete_temporary_screenshot(str(capture))
    perception.delete_temporary_screenshot(str(outside))

    assert not capture.exists()
    assert outside.exists()


@pytest.mark.asyncio
async def test_hash_capture_deletes_screenshot_on_success_and_failure(tmp_path, monkeypatch):
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    monkeypatch.setattr(reliability, "_screenshot_capture_dir", lambda: str(capture_dir))

    success_path = capture_dir / "success.png"
    _image(success_path)

    async def success_capture():
        return str(success_path)

    monkeypatch.setattr(reliability, "_capture_screenshot", success_capture)
    screen_hash, path = await _capture_screen_hash()
    assert screen_hash
    assert path == ""
    assert not success_path.exists()

    failure_path = capture_dir / "failure.png"
    _image(failure_path)

    async def failure_capture():
        return str(failure_path)

    monkeypatch.setattr(reliability, "_capture_screenshot", failure_capture)
    monkeypatch.setattr(Image, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("read failed")))
    screen_hash, path = await _capture_screen_hash()
    assert screen_hash == ""
    assert path == ""
    assert not failure_path.exists()


@pytest.mark.asyncio
async def test_capture_screenshot_cleans_up_after_capture_timeout(tmp_path, monkeypatch):
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    monkeypatch.setattr(perception, "_screenshot_capture_dir", lambda: str(capture_dir))
    monkeypatch.setattr(perception, "IS_WINDOWS", True)

    async def timed_out_capture(path):
        _image(path)
        raise asyncio.TimeoutError

    # capture_screenshot imports this helper lazily.  Make the capture layer
    # itself time out after writing a partial image, which exercises the same
    # cleanup branch without relying on the test runner's event-loop timing.
    import windows_desktop
    monkeypatch.setattr(windows_desktop, "capture_screenshot", timed_out_capture)
    assert await perception.capture_screenshot() is None
    assert list(capture_dir.glob("*.png")) == []


@pytest.mark.asyncio
async def test_agent_cleans_request_capture_when_cancelled(tmp_path, monkeypatch):
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    capture = capture_dir / "request.png"
    _image(capture)
    monkeypatch.setattr(perception, "_screenshot_capture_dir", lambda: str(capture_dir))

    agent = AdeleAgentV2(persist=False)

    async def cancelled(*_args, **_kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(agent, "_run_impl", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await agent.run("look at this", perception.ContextSnapshot(screenshot_path=str(capture)))
    assert not capture.exists()


@pytest.mark.asyncio
async def test_visual_verifier_uses_injected_router_and_redacts_capture_path(tmp_path, monkeypatch):
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    capture = capture_dir / "visual.png"
    _image(capture)
    monkeypatch.setattr(perception, "_screenshot_capture_dir", lambda: str(capture_dir))

    class Router:
        def __init__(self):
            self.calls = []

        async def route_and_call(self, **kwargs):
            self.calls.append(kwargs)
            return type("Response", (), {"text": "YES confirmed"})()

    router = Router()
    verifier = ToolVerifier(router=router)
    result = await verifier._evaluate_visual_evidence(
        tool_name="click_ui",
        tool_args={"text": "Continue"},
        string_result=VerificationResult(True, 0.7, "clicked"),
        visual_summary=f"Screen ready\nScreenshot: {capture}",
    )

    assert result is not None
    assert len(router.calls) == 1
    assert str(capture) not in router.calls[0]["user_message"]
    assert not capture.exists()


def test_agent_verifier_uses_its_existing_router():
    agent = AdeleAgentV2(persist=False)
    assert agent.verifier._router is agent.router
