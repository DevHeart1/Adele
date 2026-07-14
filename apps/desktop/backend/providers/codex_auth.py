"""ChatGPT-only authentication state around the Codex App Server."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from providers.codex_models import CodexModel, CodexModelUnavailable, select_build_week_model
from providers.codex_redaction import mask_email, safe_error_code
from providers.codex_rpc import CodexAuthenticationRequired, CodexNotInstalledError, CodexRpcClient


class AuthState(str, Enum):
    RUNTIME_MISSING = "RUNTIME_MISSING"
    STARTING_RUNTIME = "STARTING_RUNTIME"
    SIGNED_OUT = "SIGNED_OUT"
    LOGIN_STARTING = "LOGIN_STARTING"
    LOGIN_PENDING = "LOGIN_PENDING"
    AUTHENTICATED = "AUTHENTICATED"
    CHECKING_MODELS = "CHECKING_MODELS"
    READY = "READY"
    LOGGING_OUT = "LOGGING_OUT"
    ERROR = "ERROR"


@dataclass
class AuthSnapshot:
    state: str = AuthState.STARTING_RUNTIME.value
    authenticated: bool = False
    accountType: str | None = None
    email: str | None = None
    planType: str | None = None
    model: str | None = None
    displayModel: str | None = None
    reasoningEffort: str | None = None
    runtimeVersion: str | None = None
    errorCode: str | None = None
    message: str | None = None

    def public(self) -> dict[str, Any]:
        return asdict(self)


class CodexAuthService:
    """Never reads auth.json, tokens, cookies, or passwords.

    All credential storage and refresh remains inside the child Codex process.
    """

    def __init__(self, client: CodexRpcClient) -> None:
        self.client = client
        self.snapshot = AuthSnapshot()
        self.model: CodexModel | None = None
        self._lock = asyncio.Lock()

    async def check(self) -> AuthSnapshot:
        async with self._lock:
            was_login_pending = self.snapshot.state == AuthState.LOGIN_PENDING.value
            self.snapshot = AuthSnapshot(state=AuthState.STARTING_RUNTIME.value)
            try:
                await self.client.start()
            except CodexNotInstalledError:
                self.snapshot = AuthSnapshot(state=AuthState.RUNTIME_MISSING.value, errorCode="runtime_missing", message="Adele requires the Codex runtime.")
                return self.snapshot
            except Exception as exc:
                self.snapshot = AuthSnapshot(state=AuthState.ERROR.value, errorCode=safe_error_code(exc), message="Could not start the Codex runtime.")
                return self.snapshot
            self.snapshot.runtimeVersion = self.client.runtime_version
            try:
                response = await self.client.call("account/read", {"refreshToken": False}, timeout=20)
            except Exception as exc:
                self.snapshot.state = AuthState.ERROR.value
                self.snapshot.errorCode = safe_error_code(exc)
                self.snapshot.message = "Could not check the ChatGPT connection."
                return self.snapshot
            account = response.get("account") if isinstance(response, dict) else None
            if not isinstance(account, dict) or account.get("type") != "chatgpt":
                if was_login_pending:
                    self.snapshot = AuthSnapshot(
                        state=AuthState.LOGIN_PENDING.value,
                        runtimeVersion=self.client.runtime_version,
                        message="Complete sign-in in your browser.",
                    )
                    return self.snapshot
                self.snapshot = AuthSnapshot(state=AuthState.SIGNED_OUT.value, runtimeVersion=self.client.runtime_version, message="Sign in with ChatGPT to use Adele.")
                return self.snapshot
            self.snapshot = AuthSnapshot(
                state=AuthState.AUTHENTICATED.value,
                authenticated=True,
                accountType="chatgpt",
                email=mask_email(account.get("email")),
                planType=str(account.get("planType") or "unknown"),
                runtimeVersion=self.client.runtime_version,
            )
            return await self._discover_models()

    async def _discover_models(self) -> AuthSnapshot:
        self.snapshot.state = AuthState.CHECKING_MODELS.value
        try:
            response = await self.client.call("model/list", {"limit": 100, "includeHidden": False}, timeout=30)
            models = response.get("data", []) if isinstance(response, dict) else []
            self.model = select_build_week_model(models)
        except CodexModelUnavailable:
            self.model = None
            self.snapshot.state = AuthState.ERROR.value
            self.snapshot.errorCode = "model_unavailable"
            self.snapshot.message = "GPT-5.6 is not available for this ChatGPT account or workspace."
            return self.snapshot
        except Exception as exc:
            self.model = None
            self.snapshot.state = AuthState.ERROR.value
            self.snapshot.errorCode = safe_error_code(exc)
            self.snapshot.message = "Could not discover available Codex models."
            return self.snapshot
        effort = self.model.default_reasoning_effort
        self.snapshot.model = self.model.model
        self.snapshot.displayModel = self.model.display_name
        self.snapshot.reasoningEffort = effort
        self.snapshot.state = AuthState.READY.value
        self.snapshot.errorCode = None
        self.snapshot.message = None
        return self.snapshot

    async def start_login(self, *, device_code: bool = False) -> dict[str, str | None]:
        async with self._lock:
            if self.snapshot.state == AuthState.RUNTIME_MISSING.value:
                await self.check()
            await self.client.start()
            self.snapshot.state = AuthState.LOGIN_STARTING.value
            login_type = "chatgptDeviceCode" if device_code else "chatgpt"
            params: dict[str, Any] = {"type": login_type}
            if not device_code:
                params.update({"appBrand": "chatgpt", "useHostedLoginSuccessPage": True})
            try:
                response = await self.client.call("account/login/start", params, timeout=30)
            except Exception as exc:
                self.snapshot.state = AuthState.ERROR.value
                self.snapshot.errorCode = safe_error_code(exc)
                self.snapshot.message = "Could not start ChatGPT sign-in."
                return {"type": "error", "errorCode": self.snapshot.errorCode}
            if response.get("type") not in {"chatgpt", "chatgptDeviceCode"}:
                self.snapshot.state = AuthState.ERROR.value
                self.snapshot.errorCode = "unsupported_auth_mode"
                self.snapshot.message = "Adele requires ChatGPT sign-in."
                return {"type": "error", "errorCode": self.snapshot.errorCode}
            self.snapshot.state = AuthState.LOGIN_PENDING.value
            self.snapshot.message = "Complete sign-in in your browser."
            return {
                "type": str(response.get("type")),
                "authUrl": str(response.get("authUrl") or response.get("verificationUrl") or "") or None,
                "userCode": str(response.get("userCode") or "") or None,
            }

    async def cancel_login(self) -> AuthSnapshot:
        try:
            await self.client.call("account/login/cancel", {}, timeout=15)
        except Exception:
            pass
        self.snapshot.state = AuthState.SIGNED_OUT.value
        self.snapshot.authenticated = False
        self.snapshot.message = "ChatGPT sign-in was not completed."
        return self.snapshot

    async def logout(self) -> AuthSnapshot:
        self.snapshot.state = AuthState.LOGGING_OUT.value
        try:
            await self.client.call("account/logout", {}, timeout=20)
        except Exception as exc:
            self.snapshot.state = AuthState.ERROR.value
            self.snapshot.errorCode = safe_error_code(exc)
            self.snapshot.message = "Could not sign out of ChatGPT."
            return self.snapshot
        self.model = None
        self.snapshot = AuthSnapshot(state=AuthState.SIGNED_OUT.value, runtimeVersion=self.client.runtime_version, message="Signed out of ChatGPT.")
        return self.snapshot

    async def ensure_ready(self) -> CodexModel:
        state = await self.check()
        if state.state != AuthState.READY.value or not self.model:
            raise CodexAuthenticationRequired(state.message or "ChatGPT sign-in is required.")
        return self.model
