"""GPT-5.6 provider backed by one ChatGPT-authenticated Codex App Server."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

from providers.base import LLMProvider, LLMResponse, ToolCall
from providers.codex_auth import AuthState, CodexAuthService
from providers.codex_redaction import safe_error_code
from providers.codex_rpc import CodexRequestTimeout, CodexRpcClient, CodexTurnFailed, CodexTurnInterrupted


@dataclass
class ExecutionTrace:
    provider: str = "codex-app-server"
    model: str = "gpt-5.6"
    reasoning_effort: str = "medium"
    status: str = "starting"
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int | None = None
    error_code: str | None = None
    rerouted: bool = False

    def public(self) -> dict[str, Any]:
        return self.__dict__.copy()


class CodexAppServerProvider(LLMProvider):
    """Adele's only active production LLM provider.

    The App Server is started once and its ChatGPT session remains entirely
    inside Codex. Adele supplies only user text, permitted screenshots, and
    tool schemas; existing Adele approval and verification execute any action.
    """

    def __init__(self, *, app_version: str = "1.0.0", executable: str | None = None) -> None:
        self._notifications: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self.client = CodexRpcClient(
            executable=executable,
            client_version=app_version,
            notification_handler=self._on_notification,
        )
        self.auth = CodexAuthService(self.client)
        self._thread_id: str | None = None
        self._turn_lock = asyncio.Lock()
        self.last_trace = ExecutionTrace()

    @property
    def name(self) -> str:
        return "ChatGPT via Codex App Server"

    @property
    def supports_vision(self) -> bool:
        return bool(self.auth.model and self.auth.model.supports_images)

    @property
    def supports_tools(self) -> bool:
        # Adele validates its own structured calls; App Server dynamic tools are
        # deliberately feature-gated until an approval bridge is enabled.
        return True

    @property
    def model_name(self) -> str:
        return self.auth.model.model if self.auth.model else "gpt-5.6"

    async def is_available(self) -> bool:
        try:
            return (await self.auth.check()).state == AuthState.READY.value
        except Exception:
            return False

    async def close(self) -> None:
        await self.client.close()

    async def _on_notification(self, method: str, params: dict[str, Any]) -> None:
        await self._notifications.put((method, params))

    def _message_text(self, messages: list[dict], system_prompt: str) -> str:
        parts = [system_prompt.strip()] if system_prompt.strip() else []
        for message in messages:
            role = str(message.get("role") or "user")
            content = message.get("content")
            if isinstance(content, str):
                parts.append(f"{role}: {content}")
                continue
            for part in message.get("parts") or []:
                if isinstance(part, dict) and part.get("text"):
                    parts.append(f"{role}: {part['text']}")
        return "\n\n".join(parts).strip()

    async def _ensure_thread(self, model: str) -> str:
        if self._thread_id:
            return self._thread_id
        result = await self.client.call(
            "thread/start",
            {
                "model": model,
                "cwd": os.getcwd(),
                "sandbox": "read-only",
                "approvalPolicy": "never",
                "ephemeral": True,
                "developerInstructions": "You are Adele's reasoning component. Do not execute desktop actions. Return concise, user-safe plans and tool selections only.",
            },
            timeout=30,
        )
        thread = result.get("thread") if isinstance(result, dict) else {}
        thread_id = str((thread or {}).get("id") or result.get("threadId") or "")
        if not thread_id:
            raise CodexTurnFailed("Codex did not return a thread identifier.")
        self._thread_id = thread_id
        return thread_id

    def _schema_for_tools(self, tools: list[dict]) -> dict[str, Any] | None:
        if not tools:
            return None
        allowed = []
        for tool in tools:
            name = str(tool.get("name") or tool.get("function", {}).get("name") or "")
            if name:
                allowed.append(name)
        if not allowed:
            return None
        return {
            "type": "object",
            "required": ["message", "tool_calls"],
            "properties": {
                "message": {"type": "string"},
                "tool_calls": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "arguments"],
                        "properties": {
                            "name": {"type": "string", "enum": allowed},
                            "arguments": {"type": "object"},
                        },
                    },
                },
            },
        }

    @staticmethod
    def _tool_contract_prompt(prompt: str, tools: list[dict]) -> str:
        """Request Adele's validated tool envelope without App Server outputSchema."""
        names = sorted({
            str(item.get("name") or item.get("function", {}).get("name") or "").strip()
            for item in tools
        } - {""})
        if not names:
            return prompt
        return (
            f"{prompt}\n\n"
            "If you need an Adele tool, return only one JSON object with this shape: "
            '{"message":"brief user-facing update","tool_calls":[{"name":"allowed tool name","arguments":{}}]}. '
            "If no tool is needed, return the same object with an empty tool_calls array. "
            f"Allowed tool names: {', '.join(names)}."
        )

    def _parse_result(self, text: str, tools: list[dict]) -> tuple[str, list[ToolCall]]:
        if not tools:
            return text, []
        names = {str(item.get("name") or item.get("function", {}).get("name") or "") for item in tools}
        candidate = text.strip()
        if candidate.startswith("```"):
            first_newline = candidate.find("\n")
            candidate = candidate[first_newline + 1:] if first_newline >= 0 else ""
            if candidate.rstrip().endswith("```"):
                candidate = candidate.rstrip()[:-3].strip()
        try:
            parsed = json.loads(candidate)
        except (TypeError, json.JSONDecodeError):
            return text, []
        if not isinstance(parsed, dict):
            return text, []
        calls = []
        for item in parsed.get("tool_calls", []):
            if not isinstance(item, dict) or item.get("name") not in names or not isinstance(item.get("arguments"), dict):
                continue
            calls.append(ToolCall(name=item["name"], args=item["arguments"]))
        return str(parsed.get("message") or ""), calls

    @staticmethod
    def _item_text(value: Any) -> str:
        if isinstance(value, dict):
            if value.get("type") == "agentMessage":
                return str(value.get("text") or value.get("content") or "")
            for key in ("text", "content", "message"):
                if isinstance(value.get(key), str):
                    return value[key]
            for item in value.values():
                text = CodexAppServerProvider._item_text(item)
                if text:
                    return text
        if isinstance(value, list):
            return "".join(CodexAppServerProvider._item_text(item) for item in value)
        return ""

    async def _run_turn(self, *, prompt: str, image_data: bytes | None, thinking_level: str | None, tools: list[dict], response_json_schema: dict | None, stream_queue: asyncio.Queue[LLMResponse] | None = None) -> LLMResponse:
        model = await self.auth.ensure_ready()
        thread_id = await self._ensure_thread(model.model)
        effort = (thinking_level or model.default_reasoning_effort).lower()
        if model.reasoning_efforts and effort not in {item.lower() for item in model.reasoning_efforts}:
            effort = model.default_reasoning_effort
        self.last_trace = ExecutionTrace(model=model.model, reasoning_effort=effort, status="running")
        inputs: list[dict[str, Any]] = [{"type": "text", "text": self._tool_contract_prompt(prompt, tools)}]
        screenshot_path: str | None = None
        if image_data:
            if not model.supports_images:
                return LLMResponse(error="GPT-5.6 is not available with image input for this account.", provider=self.name, model=model.model)
            handle = tempfile.NamedTemporaryFile(prefix="adele-codex-", suffix=".png", delete=False)
            try:
                handle.write(image_data)
                screenshot_path = handle.name
            finally:
                handle.close()
            inputs.append({"type": "localImage", "path": screenshot_path, "detail": "auto"})
        try:
            streamed_text = ""
            # Codex App Server 0.144.2 accepts outputSchema in its protocol but
            # GPT-5.6-Sol terminates both planner and tool-envelope turns with a
            # system error when it is supplied.  Adele requests the same JSON
            # shapes in prompt text and continues to validate tool calls locally.
            del response_json_schema
            result = await self.client.call(
                "turn/start",
                {
                    "threadId": thread_id,
                    "input": inputs,
                    "model": model.model,
                    "effort": effort,
                    "outputSchema": None,
                },
                timeout=45,
            )
            turn = result.get("turn") if isinstance(result, dict) else {}
            turn_id = str((turn or {}).get("id") or result.get("turnId") or "")
            final_text = self._item_text((turn or {}).get("items", []))
            while True:
                method, params = await self._notifications.get()
                if params.get("threadId") != thread_id:
                    continue
                if turn_id and params.get("turnId") not in {None, turn_id}:
                    continue
                if method == "item/agentMessage/delta":
                    delta = str(params.get("delta") or "")
                    final_text += delta
                    streamed_text += delta
                    if stream_queue is not None and delta:
                        await stream_queue.put(LLMResponse(text=delta, provider=self.name, model=model.model, reasoning_effort=effort))
                elif method == "thread/tokenUsage/updated":
                    usage = params.get("tokenUsage", {}).get("last", {})
                    self.last_trace.input_tokens = int(usage.get("inputTokens") or 0)
                    self.last_trace.output_tokens = int(usage.get("outputTokens") or 0)
                elif method == "model/rerouted":
                    self.last_trace.rerouted = True
                elif method == "turn/completed":
                    completed = params.get("turn") or {}
                    self.last_trace.duration_ms = completed.get("durationMs")
                    status = completed.get("status")
                    if status == "interrupted":
                        raise CodexTurnInterrupted("Codex turn was interrupted.")
                    if status != "completed":
                        raise CodexTurnFailed("Codex turn failed.")
                    final_text = self._item_text(completed.get("items", [])) or final_text
                    break
            self.last_trace.status = "completed"
            text, tool_calls = self._parse_result(final_text, tools)
            # App Server's completed turn contains a full message snapshot.
            # Stream consumers append chunks, so return only the not-yet-seen
            # suffix on the terminal response rather than replaying deltas.
            if stream_queue is not None and streamed_text and text.startswith(streamed_text):
                text = text[len(streamed_text):]
            return LLMResponse(text=text, tool_calls=tool_calls, provider=self.name, model=model.model, reasoning_effort=effort, usage={"input": self.last_trace.input_tokens, "output": self.last_trace.output_tokens}, trace=self.last_trace.public())
        except (CodexTurnInterrupted, CodexTurnFailed, CodexRequestTimeout) as exc:
            self.last_trace.status = "failed"
            self.last_trace.error_code = safe_error_code(exc)
            return LLMResponse(error="Codex could not complete that request.", provider=self.name, model=model.model, trace=self.last_trace.public())
        finally:
            if screenshot_path:
                Path(screenshot_path).unlink(missing_ok=True)

    async def generate(self, messages: list[dict], system_prompt: str, tools: list[dict], image_data: bytes | None = None, temperature: float = 0.7, thinking_level: str | None = None, response_json_schema: dict | None = None, enable_builtin_tools: bool = True) -> LLMResponse:
        del temperature, enable_builtin_tools
        async with self._turn_lock:
            return await self._run_turn(prompt=self._message_text(messages, system_prompt), image_data=image_data, thinking_level=thinking_level, tools=tools or [], response_json_schema=response_json_schema)

    async def generate_stream(self, messages: list[dict], system_prompt: str, tools: list[dict], image_data: bytes | None = None, temperature: float = 0.7, thinking_level: str | None = None, response_json_schema: dict | None = None, enable_builtin_tools: bool = True) -> AsyncIterator[LLMResponse]:
        del temperature, enable_builtin_tools
        queue: asyncio.Queue[LLMResponse | None] = asyncio.Queue()

        async def run() -> None:
            async with self._turn_lock:
                response = await self._run_turn(prompt=self._message_text(messages, system_prompt), image_data=image_data, thinking_level=thinking_level, tools=tools or [], response_json_schema=response_json_schema, stream_queue=queue)
                await queue.put(response)
                await queue.put(None)

        task = asyncio.create_task(run())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            if not task.done():
                task.cancel()
