"""
ADELE - Google GenAI Provider
=============================
Gemini 3 Flash via generateContent — vision, function calling,
built-in search/code/URL tools, thinking levels, structured JSON output.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Optional, AsyncIterator
from functools import partial

from providers.base import LLMProvider, LLMResponse, ToolCall

print = partial(print, flush=True)

DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"

MILESTONE_PLAN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "task_summary": {"type": "string"},
        "needs_clarification": {"type": "boolean"},
        "clarification_prompt": {"type": "string"},
        "milestones": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "goal": {"type": "string"},
                    "success_signal": {"type": "string"},
                    "hint_tools": {"type": "array", "items": {"type": "string"}},
                    "depends_on": {"type": "array", "items": {"type": "integer"}},
                    "deliverable_key": {"type": "string"},
                },
                "required": ["id", "goal", "success_signal"],
            },
        },
    },
    "required": ["task_summary", "needs_clarification", "milestones"],
}

MEMORY_CURATOR_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "store": {"type": "boolean"},
        "category": {"type": "string"},
        "title": {"type": "string"},
        "content": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["store"],
}


def _normalize_thinking_level(level: Optional[str]) -> Optional[str]:
    if not level:
        return None
    normalized = str(level).strip().upper()
    aliases = {
        "MINIMAL": "MINIMAL",
        "LOW": "LOW",
        "MEDIUM": "MEDIUM",
        "HIGH": "HIGH",
    }
    return aliases.get(normalized)


def _resolve_thinking_level(
    explicit: Optional[str],
    *,
    temperature: float,
    response_json_schema: Optional[dict],
) -> Optional[str]:
    resolved = _normalize_thinking_level(explicit)
    if resolved:
        return resolved
    if response_json_schema is not None:
        return "HIGH"
    if temperature <= 0.05:
        return "LOW"
    if temperature <= 0.15:
        return "MEDIUM"
    return "MEDIUM"


class GeminiProvider(LLMProvider):
    """Google Gemini via generateContent / generateContentStream."""

    def __init__(self, api_key: str, model: str = DEFAULT_GEMINI_MODEL):
        self._model = (model or DEFAULT_GEMINI_MODEL).strip()
        self._api_key = api_key
        self._client: Any = None
        self._genai_types: Any = None

        if api_key:
            try:
                from google import genai
                from google.genai import types as genai_types

                self._client = genai.Client(api_key=api_key)
                self._genai_types = genai_types
                print(f"[Gemini] Client initialized (model: {self._model})")
            except ImportError:
                print("[Gemini] google-genai not installed")
            except Exception as exc:
                print(f"[Gemini] Init error: {exc}")

    @property
    def name(self) -> str:
        return f"gemini ({self._model})"

    @property
    def supports_vision(self) -> bool:
        return True

    @property
    def supports_tools(self) -> bool:
        return True

    async def is_available(self) -> bool:
        return self._client is not None

    def _build_tools(
        self,
        tools: list[dict],
        *,
        enable_builtin_tools: bool,
    ) -> list[Any]:
        types = self._genai_types
        built: list[Any] = []

        if enable_builtin_tools:
            built.extend(
                [
                    types.Tool(google_search=types.GoogleSearch()),
                    types.Tool(code_execution=types.ToolCodeExecution()),
                    types.Tool(url_context=types.UrlContext()),
                ]
            )

        if tools:
            built.append(
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t["name"],
                            description=t.get("description") or "",
                            parameters=t.get("parameters") or {"type": "object", "properties": {}},
                        )
                        for t in tools
                    ]
                )
            )

        return built

    def _build_config(
        self,
        *,
        system_prompt: str,
        tools: list[dict],
        temperature: float,
        thinking_level: Optional[str],
        response_json_schema: Optional[dict],
        enable_builtin_tools: bool,
    ) -> Any:
        types = self._genai_types
        config_kwargs: dict[str, Any] = {
            "system_instruction": system_prompt or None,
            "temperature": temperature,
        }

        tool_decls = self._build_tools(tools, enable_builtin_tools=enable_builtin_tools)
        if tool_decls:
            config_kwargs["tools"] = tool_decls

        resolved_thinking = _resolve_thinking_level(
            thinking_level,
            temperature=temperature,
            response_json_schema=response_json_schema,
        )
        if resolved_thinking and "gemma" not in self._model.lower():
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=resolved_thinking,
            )

        if response_json_schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_json_schema"] = response_json_schema

        return types.GenerateContentConfig(**config_kwargs)

    def _normalize_contents(self, messages: list[dict], image_data: Optional[bytes] = None) -> list[dict]:
        types = self._genai_types
        contents: list[dict] = []

        for message in messages:
            msg = dict(message)
            if "parts" in msg:
                new_parts = []
                for part in msg["parts"]:
                    if isinstance(part, dict) and "function_response" in part:
                        fr = part["function_response"]
                        new_parts.append(
                            types.Part.from_function_response(
                                name=fr["name"],
                                response=fr.get("response") or {},
                            )
                        )
                    else:
                        new_parts.append(part)
                msg["parts"] = new_parts
            contents.append(msg)

        if image_data and contents and contents[-1].get("role") == "user":
            img_part = types.Part.from_bytes(data=image_data, mime_type="image/png")
            contents[-1] = dict(contents[-1])
            contents[-1]["parts"] = list(contents[-1].get("parts", [])) + [img_part]

        return contents

    def _parse_candidate_parts(self, parts: list[Any]) -> LLMResponse:
        result = LLMResponse(provider=self.name)
        result.raw_model_parts = parts
        text_chunks: list[str] = []

        for part in parts or []:
            if getattr(part, "function_call", None):
                fc = part.function_call
                result.tool_calls.append(
                    ToolCall(
                        name=fc.name,
                        args=dict(fc.args) if fc.args else {},
                    )
                )
            elif getattr(part, "text", None):
                text_chunks.append(part.text)
            elif getattr(part, "executable_code", None):
                code = part.executable_code
                code_text = getattr(code, "code", None) or str(code)
                text_chunks.append(f"\n[code]\n{code_text}\n")
            elif getattr(part, "code_execution_result", None):
                cer = part.code_execution_result
                output = getattr(cer, "output", None) or str(cer)
                text_chunks.append(f"\n[code result]\n{output}\n")

        if text_chunks:
            result.text = "".join(text_chunks).strip()

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
        if not self._client:
            return LLMResponse(error="Gemini client not initialized", provider=self.name)

        contents = self._normalize_contents(messages, image_data=image_data)
        config = self._build_config(
            system_prompt=system_prompt,
            tools=tools,
            temperature=temperature,
            thinking_level=thinking_level,
            response_json_schema=response_json_schema,
            enable_builtin_tools=enable_builtin_tools,
        )

        max_api_retries = 3
        last_error: Optional[Exception] = None

        for api_attempt in range(max_api_retries + 1):
            try:
                response = await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model=self._model,
                        contents=contents,
                        config=config,
                    ),
                    timeout=90.0,
                )

                candidate = response.candidates[0] if response.candidates else None
                if not candidate:
                    if api_attempt < max_api_retries:
                        await asyncio.sleep(2.0 * (api_attempt + 1))
                        continue
                    return LLMResponse(text="I'm not sure how to help with that.", provider=self.name)

                content = getattr(candidate, "content", None)
                if not content or not getattr(content, "parts", None):
                    if api_attempt < max_api_retries:
                        await asyncio.sleep(2.0 * (api_attempt + 1))
                        continue
                    return LLMResponse(text="I'm not sure how to help with that.", provider=self.name)

                result = self._parse_candidate_parts(content.parts)
                if result.text is None and not result.tool_calls:
                    if api_attempt < max_api_retries:
                        print(f"[Gemini] Empty response (attempt {api_attempt + 1}), retrying...")
                        await asyncio.sleep(2.0 * (api_attempt + 1))
                        continue
                return result

            except Exception as exc:
                last_error = exc
                if api_attempt < max_api_retries:
                    print(f"[Gemini] API error (attempt {api_attempt + 1}): {exc}")
                    await asyncio.sleep(2.5 * (api_attempt + 1))
                    continue
                return LLMResponse(error=f"Gemini API error: {last_error}", provider=self.name)

        return LLMResponse(error=f"Gemini API error: {last_error}", provider=self.name)

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
            yield LLMResponse(error="Gemini client not initialized", provider=self.name)
            return

        contents = self._normalize_contents(messages, image_data=image_data)
        config = self._build_config(
            system_prompt=system_prompt,
            tools=tools,
            temperature=temperature,
            thinking_level=thinking_level,
            response_json_schema=response_json_schema,
            enable_builtin_tools=enable_builtin_tools,
        )

        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self._model,
                contents=contents,
                config=config,
            )

            async def iterate_with_timeout():
                stream_iter = stream.__aiter__()
                while True:
                    try:
                        chunk = await asyncio.wait_for(stream_iter.__anext__(), timeout=90.0)
                        yield chunk
                    except StopAsyncIteration:
                        break

            async for chunk in iterate_with_timeout():
                if not chunk.candidates or not chunk.candidates[0].content or not chunk.candidates[0].content.parts:
                    continue
                parsed = self._parse_candidate_parts(chunk.candidates[0].content.parts)
                if parsed.text or parsed.tool_calls:
                    yield parsed

        except Exception as exc:
            yield LLMResponse(error=f"Gemini streaming error: {exc}", provider=self.name)
