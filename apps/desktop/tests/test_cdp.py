"""
Automated tests for Chrome DevTools Protocol (CDP) client and integration.
"""

import os
import sys

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.join(repo_root, "backend"))

import json
import pytest
from unittest.mock import AsyncMock, patch

from browser.cdp import CDPClient, cdp_client
from browser.resolver import BrowserResolver
from agent.local_action_contract import AdeleLocalActionContract


class MockResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


class MockWebSocket:
    def __init__(self, responses):
        self.responses = responses
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def send(self, data):
        self.sent.append(json.loads(data))

    async def recv(self):
        if self.responses:
            return self.responses.pop(0)
        return json.dumps({"id": 1, "result": {"result": {"type": "string", "value": "null"}}})


@pytest.mark.asyncio
async def test_find_page_target():
    client = CDPClient(ports=[9222])
    mock_targets = [
        {"type": "background_page", "webSocketDebuggerUrl": "ws://1"},
        {"type": "page", "webSocketDebuggerUrl": "ws://2"},
    ]

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = MockResponse(200, mock_targets)
        target = await client.find_page_target()
        assert target is not None
        assert target["type"] == "page"
        assert target["webSocketDebuggerUrl"] == "ws://2"
        assert target["port"] == 9222


@pytest.mark.asyncio
async def test_evaluate_js():
    client = CDPClient(ports=[9222])
    mock_targets = [{"type": "page", "webSocketDebuggerUrl": "ws://2"}]
    mock_ws = MockWebSocket([
        json.dumps({"id": 1, "result": {"result": {"type": "string", "value": "test-val"}}})
    ])

    with patch("httpx.AsyncClient.get", return_value=MockResponse(200, mock_targets)):
        with patch("websockets.connect", return_value=mock_ws):
            val = await client.evaluate_js("1 + 1")
            assert val == "test-val"
            assert len(mock_ws.sent) == 1
            assert mock_ws.sent[0]["method"] == "Runtime.evaluate"
            assert mock_ws.sent[0]["params"]["expression"] == "1 + 1"


@pytest.mark.asyncio
async def test_resolve_element_via_cdp():
    client = CDPClient(ports=[9222])
    mock_targets = [{"type": "page", "webSocketDebuggerUrl": "ws://2"}]
    mock_element_data = {
        "label": "Submit",
        "screenX": 100,
        "screenY": 200,
        "width": 80,
        "height": 30,
        "score": 90.0,
    }
    mock_ws = MockWebSocket([
        json.dumps({"id": 1, "result": {"result": {"type": "string", "value": json.dumps(mock_element_data)}}})
    ])

    with patch("httpx.AsyncClient.get", return_value=MockResponse(200, mock_targets)):
        with patch("websockets.connect", return_value=mock_ws):
            res = await client.resolve_element_via_cdp("Submit button")
            assert res is not None
            assert res["label"] == "Submit"
            assert res["screenX"] == 100
            assert res["screenY"] == 200


@pytest.mark.asyncio
async def test_browser_resolver_delegates_to_cdp():
    resolver = BrowserResolver()
    mock_element_data = {
        "label": "Continue",
        "screenX": 300,
        "screenY": 400,
        "width": 100,
        "height": 40,
        "score": 95.0,
    }

    with patch("browser.cdp.CDPClient.resolve_element_via_cdp") as mock_resolve:
        mock_resolve.return_value = mock_element_data
        element = await resolver.resolve_via_cdp("Continue", action="click")

        assert element is not None
        assert element.ref_id == "cdp_match"
        assert element.text == "Continue"
        assert element.bounds["x"] == 300
        assert element.bounds["y"] == 400
        assert element.bounds["mid_x"] == 350
        assert element.bounds["mid_y"] == 420


@pytest.mark.asyncio
async def test_action_contract_ground_target_fallback():
    contract = AdeleLocalActionContract()
    mock_element_data = {
        "label": "Submit",
        "screenX": 150,
        "screenY": 250,
        "width": 60,
        "height": 20,
        "score": 88.0,
    }

    # Force browser_bridge to be disconnected
    with patch("browser.bridge.BrowserBridge.is_connected", return_value=False):
        with patch("browser.cdp.CDPClient.resolve_element_via_cdp", return_value=mock_element_data):
            res = await contract.ground_target(query="Submit", action="click")
            assert res["ok"] is True
            assert res["status"] == "grounded"
            assert res["source"] == "cdp"
            assert res["target"]["ref_id"] == "cdp_match"
            assert res["target"]["x"] == 180
            assert res["target"]["y"] == 260


@pytest.mark.asyncio
async def test_action_contract_act_via_cdp():
    contract = AdeleLocalActionContract()

    with patch("browser.cdp.CDPClient.cdp_click") as mock_click:
        mock_click.return_value = {"ok": True, "message": "Clicked element via CDP", "label": "Click me"}
        
        payload = {
            "action": "click",
            "ref_id": "cdp_match",
            "source": "cdp",
            "query": "Click me",
            "mode": "assist",
            "confirmed": True,
        }
        res = await contract.act(payload)
        assert res["ok"] is True
        assert res["status"] == "acted"
        assert res["cdp_result"]["ok"] is True
        mock_click.assert_called_once_with("Click me")

