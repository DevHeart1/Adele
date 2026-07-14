from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from providers.codex_app_server import CodexAppServerProvider
from providers.codex_auth import AuthState, CodexAuthService
from providers.codex_models import CodexModelUnavailable, select_build_week_model
from providers.codex_redaction import redact_text
from providers.codex_rpc import CodexRpcClient


FAKE_SERVER = Path(__file__).with_name("fake_codex_app_server.py")


def fake_client(notification_handler=None) -> CodexRpcClient:
    return CodexRpcClient(
        executable=sys.executable,
        command_args=(str(FAKE_SERVER),),
        notification_handler=notification_handler,
    )


@pytest.mark.asyncio
async def test_initialization_account_and_model_discovery():
    client = fake_client()
    auth = CodexAuthService(client)
    state = await auth.check()
    assert state.state == AuthState.READY.value
    assert state.model == "gpt-5.6"
    assert state.email == "j***@example.com"
    await client.close()


@pytest.mark.asyncio
async def test_browser_and_device_chatgpt_login_only():
    client = fake_client()
    auth = CodexAuthService(client)
    await auth.check()
    browser = await auth.start_login()
    device = await auth.start_login(device_code=True)
    assert browser["type"] == "chatgpt"
    assert browser["authUrl"].startswith("https://")
    assert device["type"] == "chatgptDeviceCode"
    assert device["userCode"] == "FAKE-CODE"
    await client.close()


@pytest.mark.asyncio
async def test_provider_streams_final_response_and_safe_usage():
    provider = CodexAppServerProvider()
    provider.client = fake_client(provider._on_notification)
    provider.auth.client = provider.client
    chunks = [chunk async for chunk in provider.generate_stream(
        messages=[{"role": "user", "parts": [{"text": "Say hello"}]}],
        system_prompt="",
        tools=[],
    )]
    assert any(chunk.text == "hello " for chunk in chunks)
    assert chunks[-1].text == "hello world"
    assert chunks[-1].usage == {"input": 3, "output": 2}
    await provider.close()


def test_build_week_model_is_strict_and_redaction_hides_secrets():
    with pytest.raises(CodexModelUnavailable):
        select_build_week_model([])
    redacted = redact_text("Bearer abcdefghijklmnop https://auth.openai.com/token C:\\Users\\Ada\\secret.txt")
    assert "abcdefghijklmnop" not in redacted
    assert "auth.openai.com" not in redacted
    assert "C:\\Users" not in redacted
