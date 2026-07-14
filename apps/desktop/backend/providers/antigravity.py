"""
ADELE — Antigravity agent via Google GenAI Interactions API.
"""

from __future__ import annotations

import asyncio
import base64
import os
from typing import Any, AsyncIterator, Optional, Union
from functools import partial

from providers.base import LLMProvider, LLMResponse, ToolCall

print = partial(print, flush=True)

DEFAULT_ANTIGRAVITY_AGENT = "antigravity-preview-05-2026"

_BUILTIN_TOOLS: list[dict] = [
    {"type": "code_execution"},
    {"type": "google_search"},
    {"type": "url_context"},
]

_DEFAULT_ENVIRONMENT = {"type": "remote", "network": "disabled"}


def is_antigravity_agent(model_or_agent: str) -> bool:
    return "antigravity" in (model_or_agent or "").strip().lower()


def _extract_message_text(message: dict) -> str:
    parts = message.get("parts") or []
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, dict):
            if part.get("text"):
                chunks.append(str(part["text"]))
            elif part.get("function_response"):
                fr = part["function_response"]
                name = fr.get("name") or "tool"
                response = fr.get("response")
                chunks.append(f"[{name} result] {response}")
        elif isinstance(part, str):
            chunks.append(part)
        elif hasattr(part, "text") and part.text:
            chunks.append(str(part.text))
    return "\n".join(chunks).strip()


def _messages_to_input(
    messages: list[dict],
    image_data: Optional[bytes] = None,
) -> Union[str, list[dict]]:
    if not messages and image_data:
        content = [{"type": "image", "data": base64.b64encode(image_data).decode("ascii"), "mime_type": "image/png"}]
        return [{"type": "user_input", "content": content}]

    if len(messages) == 1 and not image_data:
        text = _extract_message_text(messages[0])
        parts = messages[0].get("parts") or []
        has_tool_parts = any(
            isinstance(p, dict) and ("function_response" in p or "function_call" in p)
            for p in parts
        )
        if text and not has_tool_parts:
            return text

    steps: list[dict] = []
    for message in messages:
        role = (message.get("role") or "user").lower()
        parts = message.get("parts") or []
        for part in parts:
            if isinstance(part, dict) and part.get("function_response"):
                fr = part["function_response"]
                steps.append(
                    {
                        "type": "function_result",
                        "call_id": fr.get("id") or fr.get("name") or "tool",
                        "result": fr.get("response") or {},
                    }
                )
                continue

            text = ""
            if isinstance(part, dict):
                text = str(part.get("text") or "")
            elif isinstance(part, str):
                text = part
            elif hasattr(part, "text"):
                text = str(part.text or "")

            if not text:
                continue

            if role == "model":
                steps.append(
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": text}],
                    }
                )
            else:
                steps.append(
                    {
                        "type": "user_input",
                        "content": [{"type": "text", "text": text}],
                    }
                )

    if image_data:
        steps.append(
            {
                "type": "user_input",
                "content": [
                    {
                        "type": "image",
                        "data": base64.b64encode(image_data).decode("ascii"),
                        "mime_type": "image/png",
                    }
                ],
            }
        )

    if steps:
        return steps

    fallback = _extract_message_text(messages[-1]) if messages else ""
    return fallback or ""


def _adele_tools_to_interactions(tools: list[dict]) -> list[dict]:
    interaction_tools = list(_BUILTIN_TOOLS)
    seen = {t["type"] for t in interaction_tools}

    for tool in tools or []:
        name = (tool.get("name") or "").strip()
        if not name:
            continue
        entry: dict[str, Any] = {
            "type": "function",
            "name": name,
        }
        if tool.get("description"):
            entry["description"] = tool["description"]
        if tool.get("parameters"):
            entry["parameters"] = tool["parameters"]
        interaction_tools.append(entry)
        seen.add(name)

    return interaction_tools


def _parse_interaction(interaction: Any) -> LLMResponse:
    result = LLMResponse(provider="antigravity")

    status = getattr(interaction, "status", None)
    if status == "failed":
        err = getattr(interaction, "error", None)
        message = getattr(err, "message", None) if err else None
        return LLMResponse(
            error=message or "Antigravity interaction failed",
            provider="antigravity",
        )

    for step in getattr(interaction, "steps", None) or []:
        step_type = getattr(step, "type", None)

        if step_type == "model_output":
            for content in getattr(step, "content", None) or []:
                if getattr(content, "type", None) == "text":
                    text = getattr(content, "text", None)
                    if text:
                        result.text = (result.text or "") + text

        elif step_type == "function_call":
            args = getattr(step, "arguments", None) or {}
            if not isinstance(args, dict):
                args = dict(args) if hasattr(args, "items") else {}
            name = getattr(step, "name", None) or ""
            if name:
                result.tool_calls.append(ToolCall(name=name, args=args))

    if result.text is None and not result.tool_calls:
        return LLMResponse(
            error="Antigravity returned an empty response",
            provider="antigravity",
        )

    return result


class AntigravityProvider(LLMProvider):
    """Google Antigravity agent via the Interactions API."""

    def __init__(self, api_key: str, agent: str = DEFAULT_ANTIGRAVITY_AGENT):
        self._agent = (agent or DEFAULT_ANTIGRAVITY_AGENT).strip()
        self._api_key = api_key
        self._client: Any = None
        self._previous_interaction_id: Optional[str] = None

        if api_key:
            try:
                from google import genai

                self._client = genai.Client(api_key=api_key)
                print(f"[Antigravity] Client initialized (agent: {self._agent})")
            except ImportError:
                print("[Antigravity] google-genai not installed")
            except Exception as exc:
                print(f"[Antigravity] Init error: {exc}")

    @property
    def _model(self) -> str:
        """Router compatibility — Antigravity uses agent IDs, not Gemini model names."""
        return self._agent

    @property
    def name(self) -> str:
        return f"antigravity ({self._agent})"

    @property
    def supports_vision(self) -> bool:
        return True

    @property
    def supports_tools(self) -> bool:
        return True

    async def is_available(self) -> bool:
        return self._client is not None

    def _environment(self) -> dict:
        network = (os.environ.get("ADELE_ANTIGRAVITY_NETWORK") or "disabled").strip()
        return {"type": "remote", "network": network or "disabled"}

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
        if not self._client:
            return LLMResponse(error="Antigravity client not initialized", provider=self.name)

        payload: dict[str, Any] = {
            "agent": self._agent,
            "input": _messages_to_input(messages, image_data=image_data),
            "tools": _adele_tools_to_interactions(tools),
            "environment": self._environment(),
        }
        if system_prompt:
            payload["system_instruction"] = system_prompt
        if self._previous_interaction_id:
            payload["previous_interaction_id"] = self._previous_interaction_id

        timeout_s = float(os.environ.get("ADELE_ANTIGRAVITY_TIMEOUT", "120") or 120)

        try:
            interaction = await asyncio.wait_for(
                self._client.aio.interactions.create(**payload),
                timeout=timeout_s,
            )
            if getattr(interaction, "id", None):
                self._previous_interaction_id = interaction.id
            return _parse_interaction(interaction)
        except Exception as exc:
            return LLMResponse(error=f"Antigravity API error: {exc}", provider=self.name)

    async def generate_stream(
        self,
        messages: list[dict],
        system_prompt: str,
        tools: list[dict],
        image_data: Optional[bytes] = None,
        temperature: float = 0.7,
        thinking_level: Optional[str] = None,
        response_json_schema: Optional[dict] = None,
        enable_builtin_tools: bool = True,
    ) -> AsyncIterator[LLMResponse]:
        if not self._client:
            yield LLMResponse(error="Antigravity client not initialized", provider=self.name)
            return

        payload: dict[str, Any] = {
            "agent": self._agent,
            "input": _messages_to_input(messages, image_data=image_data),
            "tools": _adele_tools_to_interactions(tools),
            "environment": self._environment(),
            "stream": True,
        }
        if system_prompt:
            payload["system_instruction"] = system_prompt
        if self._previous_interaction_id:
            payload["previous_interaction_id"] = self._previous_interaction_id

        timeout_s = float(os.environ.get("ADELE_ANTIGRAVITY_TIMEOUT", "120") or 120)

        try:
            stream = await asyncio.wait_for(
                self._client.aio.interactions.create(**payload),
                timeout=timeout_s,
            )

            async for event in stream:
                interaction_id = getattr(event, "interaction_id", None) or getattr(event, "id", None)
                if interaction_id:
                    self._previous_interaction_id = interaction_id

                event_type = getattr(event, "type", None)
                if event_type == "interaction.completed":
                    interaction = getattr(event, "interaction", None)
                    if interaction:
                        parsed = _parse_interaction(interaction)
                        if parsed.text or parsed.tool_calls:
                            yield parsed
                    continue

                delta = getattr(event, "delta", None)
                if delta is None:
                    continue

                text = getattr(delta, "text", None)
                if text:
                    yield LLMResponse(text=text, provider=self.name)

        except Exception as exc:
            response = await self.generate(
                messages=messages,
                system_prompt=system_prompt,
                tools=tools,
                image_data=image_data,
                temperature=temperature,
            )
            if response.error:
                yield LLMResponse(error=f"Antigravity streaming error: {exc}", provider=self.name)
            else:
                yield response
