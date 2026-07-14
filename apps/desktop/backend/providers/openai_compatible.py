"""
ADELE - OpenAI-compatible local provider
========================================
Supports Gemma-capable local runtimes that expose /v1/chat/completions,
including Ollama and custom OpenAI-compatible servers.
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Optional, AsyncIterator
from functools import partial

import httpx

from providers.base import LLMProvider, LLMResponse, ToolCall

print = partial(print, flush=True)


class OpenAICompatibleProvider(LLMProvider):
    """Local OpenAI-compatible chat provider."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        label: str = "local",
        supports_vision: bool = False,
        supports_tools: bool = True,
    ):
        self._base_url = (base_url or "").rstrip("/")
        self._model = (model or "").strip()
        self._api_key = api_key or "adele-local"
        self._label = label or "local"
        self._supports_vision = supports_vision
        self._supports_tools = supports_tools

    @property
    def name(self) -> str:
        return f"{self._label} ({self._model})"

    @property
    def supports_vision(self) -> bool:
        return self._supports_vision

    @property
    def supports_tools(self) -> bool:
        return self._supports_tools

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def is_available(self) -> bool:
        if not self._base_url or not self._model:
            return False
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self._base_url}/models", headers=self._headers)
                return response.status_code < 500
        except Exception as exc:
            print(f"[LocalProvider] Availability check failed for {self._base_url}: {exc}")
            return False

    def _part_text(self, part) -> str:
        if isinstance(part, str):
            return part
        if isinstance(part, dict):
            if "text" in part:
                return str(part.get("text") or "")
            if "function_response" in part:
                return json.dumps(part.get("function_response") or {}, ensure_ascii=False)
            if "function_call" in part:
                return json.dumps(part.get("function_call") or {}, ensure_ascii=False)
        text = getattr(part, "text", None)
        return str(text or "")

    def _convert_messages(self, messages: list[dict], system_prompt: str, image_data: Optional[bytes]) -> list[dict]:
        converted = []
        if system_prompt:
            converted.append({"role": "system", "content": system_prompt})

        for message in messages or []:
            role = message.get("role", "user")
            parts = message.get("parts", [])

            if role == "model":
                role = "assistant"
            elif role == "function":
                role = "tool"

            if role == "tool":
                converted.append({
                    "role": "tool",
                    "tool_call_id": message.get("tool_call_id") or message.get("name") or "adele_tool",
                    "content": " ".join(self._part_text(part) for part in parts).strip(),
                })
                continue

            text = " ".join(self._part_text(part) for part in parts).strip()
            converted.append({"role": role, "content": text})

        if image_data and converted and converted[-1]["role"] == "user":
            if not self._supports_vision:
                converted[-1]["content"] = (
                    f"{converted[-1]['content']}\n\n[ADELE note: screenshot omitted because "
                    f"{self.name} is configured as text-only.]"
                ).strip()
            else:
                encoded = base64.b64encode(image_data).decode("ascii")
                text = converted[-1].get("content", "")
                converted[-1]["content"] = [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
                ]

        return converted

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        if not tools or not self._supports_tools:
            return []
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                },
            }
            for tool in tools
        ]

    def _parse_message(self, message: dict) -> LLMResponse:
        result = LLMResponse(provider=self.name)
        content = message.get("content")
        if isinstance(content, list):
            result.text = "".join(
                str(part.get("text", "")) for part in content if isinstance(part, dict)
            ) or None
        elif content:
            result.text = str(content)

        for tool_call in message.get("tool_calls") or []:
            fn = tool_call.get("function") or {}
            name = fn.get("name")
            if not name:
                continue
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except Exception:
                args = {"_raw": raw_args}
            result.tool_calls.append(ToolCall(name=name, args=args))
        return result

    async def generate(
        self,
        messages: list[dict],
        system_prompt: str,
        tools: list[dict],
        image_data: Optional[bytes] = None,
        temperature: float = 0.7,
        thinking_level: Optional[str] = None,
        response_json_schema: Optional[dict] = None,
        enable_builtin_tools: bool = True,
    ) -> LLMResponse:
        if not self._base_url or not self._model:
            return LLMResponse(error="Local provider is not configured", provider=self.name)

        payload = {
            "model": self._model,
            "messages": self._convert_messages(messages, system_prompt, image_data),
            "temperature": temperature,
        }
        tool_payload = self._convert_tools(tools)
        if tool_payload:
            payload["tools"] = tool_payload
            payload["tool_choice"] = "auto"

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            return LLMResponse(error=f"Local provider error: {exc}", provider=self.name)

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return self._parse_message(message)

    async def generate_stream(
        self,
        messages: list[dict],
        system_prompt: str,
        tools: list[dict],
        image_data: Optional[bytes] = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[LLMResponse]:
        # Many local runtimes differ in streaming/tool-call deltas. Use the
        # stable non-streaming path and yield once.
        yield await asyncio.wait_for(
            self.generate(messages, system_prompt, tools, image_data, temperature),
            timeout=95.0,
        )
