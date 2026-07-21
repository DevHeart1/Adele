"""Deterministic stdio fake for Codex App Server integration tests."""

from __future__ import annotations

import json
import sys


def send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def notification(method, params):
    send({"jsonrpc": "2.0", "method": method, "params": params})


for raw in sys.stdin:
    try:
        request = json.loads(raw)
    except json.JSONDecodeError:
        continue
    method = request.get("method")
    params = request.get("params") or {}
    request_id = request.get("id")
    if request_id is None:
        continue
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": request_id, "result": {"codexHome": "C:/fake", "platformFamily": "windows", "platformOs": "windows", "userAgent": "codex-cli/0.144.2"}})
    elif method == "account/read":
        send({"jsonrpc": "2.0", "id": request_id, "result": {"requiresOpenaiAuth": True, "account": {"type": "chatgpt", "email": "judge@example.com", "planType": "plus"}}})
    elif method == "account/login/start":
        login_type = params.get("type")
        if login_type == "chatgpt" and ({"appBrand", "useHostedLoginSuccessPage"} & params.keys()):
            send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Hosted login handoff is not allowed"}})
            continue
        if login_type == "chatgptDeviceCode":
            result = {"type": "chatgptDeviceCode", "loginId": "fake-login", "verificationUrl": "https://chatgpt.com/auth/device", "userCode": "FAKE-CODE"}
        else:
            result = {"type": "chatgpt", "loginId": "fake-login", "authUrl": "https://auth.openai.com/fake"}
        send({"jsonrpc": "2.0", "id": request_id, "result": result})
    elif method in {"account/login/cancel", "account/logout"}:
        send({"jsonrpc": "2.0", "id": request_id, "result": {}})
    elif method == "model/list":
        model = {"id": "gpt-5.6", "model": "gpt-5.6", "displayName": "GPT-5.6", "description": "fake", "hidden": False, "isDefault": True, "defaultReasoningEffort": "medium", "supportedReasoningEfforts": [{"reasoningEffort": "low", "description": ""}, {"reasoningEffort": "medium", "description": ""}, {"reasoningEffort": "high", "description": ""}], "inputModalities": ["text", "image"]}
        send({"jsonrpc": "2.0", "id": request_id, "result": {"data": [model], "nextCursor": None}})
    elif method == "thread/start":
        send({"jsonrpc": "2.0", "id": request_id, "result": {"thread": {"id": "thread-fake"}}})
    elif method == "turn/start":
        if params.get("outputSchema") is not None:
            send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "schema-only turn rejected"}})
            continue
        turn = {"id": "turn-fake", "status": "inProgress", "items": []}
        send({"jsonrpc": "2.0", "id": request_id, "result": {"turn": turn}})
        notification("turn/started", {"threadId": "thread-fake", "turn": turn})
        notification("item/agentMessage/delta", {"threadId": "thread-fake", "turnId": "turn-fake", "itemId": "item-fake", "delta": "hello "})
        notification("thread/tokenUsage/updated", {"threadId": "thread-fake", "turnId": "turn-fake", "tokenUsage": {"last": {"inputTokens": 3, "outputTokens": 2, "cachedInputTokens": 0, "reasoningOutputTokens": 0, "totalTokens": 5}, "total": {"inputTokens": 3, "outputTokens": 2, "cachedInputTokens": 0, "reasoningOutputTokens": 0, "totalTokens": 5}}})
        notification("turn/completed", {"threadId": "thread-fake", "turn": {"id": "turn-fake", "status": "completed", "durationMs": 1, "items": [{"type": "agentMessage", "text": "hello world"}]}})
    elif method == "turn/interrupt":
        send({"jsonrpc": "2.0", "id": request_id, "result": {}})
    else:
        send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "unknown method"}})
