"""Single-provider routing facade for the Build Week desktop experience.

Legacy Gemini, Ollama, and OpenAI-compatible providers remain in the source
tree for historical experiments, but production composition uses only Codex.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from providers.base import LLMProvider, LLMResponse
from providers.codex_app_server import CodexAppServerProvider


class Tier(Enum):
    FAST = 1
    POWERFUL = 2


@dataclass
class RouteDecision:
    tier: Tier
    provider: LLMProvider
    reason: str
    model_name: str = "gpt-5.6"


class ModelRouter:
    """Compatibility facade that shares exactly one Codex provider instance."""

    def __init__(self) -> None:
        self._provider: CodexAppServerProvider | None = None
        self._initialized = False
        self._init_lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            self._provider = CodexAppServerProvider()
            # Start the runtime and expose a signed-out state without treating
            # lack of a personal login as a backend crash.
            await self._provider.auth.check()
            self._initialized = True

    @property
    def auth(self):
        return self._provider.auth if self._provider else None

    async def route(self, text: str, context_summary: str = "", has_screenshot: bool = False) -> RouteDecision:
        del text, context_summary, has_screenshot
        await self.initialize()
        if not self._provider:
            raise RuntimeError("Codex provider did not initialize.")
        return RouteDecision(
            tier=Tier.POWERFUL,
            provider=self._provider,
            reason="GPT-5.6 is the required Adele Build Week model.",
            model_name=self._provider.model_name,
        )

    async def route_and_call(self, user_message: str, system_prompt: str = "", force_tier: Optional[str] = None, image_data: Optional[bytes] = None) -> LLMResponse:
        del force_tier
        decision = await self.route(user_message, has_screenshot=image_data is not None)
        return await decision.provider.generate(
            messages=[{"role": "user", "parts": [{"text": user_message}]}],
            system_prompt=system_prompt,
            tools=[],
            image_data=image_data,
        )

    @property
    def fast(self) -> Optional[LLMProvider]:
        return self._provider

    @property
    def powerful(self) -> Optional[LLMProvider]:
        return self._provider

    @property
    def fallback(self) -> Optional[LLMProvider]:
        return self._provider

    async def shutdown(self) -> None:
        if self._provider:
            await self._provider.close()
        self._initialized = False

    def status(self) -> dict:
        snapshot = self.auth.snapshot.public() if self.auth else {"state": "STARTING_RUNTIME"}
        return {
            "provider": self._provider.name if self._provider else "ChatGPT via Codex App Server",
            "model": self._provider.model_name if self._provider else "gpt-5.6",
            "auth": snapshot,
            "legacy_providers_active": False,
        }

    @staticmethod
    def _looks_trivial_fast_request(text: str) -> bool:
        """Legacy planner hint only; routing still always selects GPT-5.6."""
        normalized = (text or "").strip().lower()
        if normalized in {"proceed", "go ahead", "yes", "approved", "start"}:
            return False
        return normalized.startswith(("open ", "launch ")) and " and " not in normalized and len(normalized) <= 50
