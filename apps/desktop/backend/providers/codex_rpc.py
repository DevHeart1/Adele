"""Safe asynchronous JSON-RPC client for ``codex app-server`` over stdio."""

from __future__ import annotations

import asyncio
import itertools
import json
import os
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from providers.codex_redaction import redact_text, safe_error_code


class CodexError(RuntimeError):
    code = "runtime_error"


class CodexNotInstalledError(CodexError):
    code = "runtime_missing"


class CodexProcessError(CodexError):
    code = "runtime_crashed"


class CodexProtocolError(CodexError):
    code = "protocol_error"


class CodexRequestTimeout(CodexError):
    code = "timeout"


class CodexAuthenticationRequired(CodexError):
    code = "authentication_required"


class CodexTurnFailed(CodexError):
    code = "turn_failed"


class CodexTurnInterrupted(CodexError):
    code = "interrupted"


NotificationHandler = Callable[[str, dict[str, Any]], Awaitable[None] | None]
ServerRequestHandler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]


class CodexRpcClient:
    """One App Server process with serialised writes and correlated requests."""

    MAX_LINE_BYTES = 2 * 1024 * 1024

    def __init__(
        self,
        *,
        executable: str | None = None,
        command_args: tuple[str, ...] = ("app-server",),
        client_version: str = "0.0.0",
        notification_handler: NotificationHandler | None = None,
        server_request_handler: ServerRequestHandler | None = None,
    ) -> None:
        self._executable = executable
        self._command_args = command_args
        self._client_version = client_version
        self._notification_handler = notification_handler
        self._server_request_handler = server_request_handler
        self._process: asyncio.subprocess.Process | None = None
        self._write_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._notification_queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._wait_task: asyncio.Task[None] | None = None
        self._initialized = False
        self.runtime_version: str | None = None
        self.last_error_code: str | None = None

    @staticmethod
    def locate_executable(override: str | None = None) -> str:
        candidate = override or os.environ.get("ADELE_CODEX_EXECUTABLE")
        if candidate:
            path = Path(candidate).expanduser()
            if path.is_file():
                return str(path)
            raise CodexNotInstalledError("Configured Codex runtime is unavailable.")
        if os.name == "nt":
            local = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin"
            for installed in sorted(local.glob("*/codex.exe"), reverse=True):
                if installed.is_file():
                    return str(installed)
        names = ("codex.exe", "codex.cmd", "codex") if os.name == "nt" else ("codex",)
        for name in names:
            found = shutil.which(name)
            if found:
                return found
        raise CodexNotInstalledError("Codex runtime is not installed or not on PATH.")

    async def start(self) -> None:
        if self._initialized:
            return
        async with self._start_lock:
            if self._initialized:
                return
            executable = self.locate_executable(self._executable)
            try:
                self._process = await asyncio.create_subprocess_exec(
                    executable, *self._command_args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=self.MAX_LINE_BYTES + 1,
                )
            except (FileNotFoundError, PermissionError, OSError) as exc:
                raise CodexNotInstalledError("Codex runtime could not be started.") from exc
            self._reader_task = asyncio.create_task(self._read_stdout(), name="adele-codex-stdout")
            self._stderr_task = asyncio.create_task(self._drain_stderr(), name="adele-codex-stderr")
            self._wait_task = asyncio.create_task(self._watch_process(), name="adele-codex-wait")
            try:
                result = await self.call(
                    "initialize",
                    {"clientInfo": {"name": "adele_desktop", "title": "Adele Desktop", "version": self._client_version}},
                    timeout=20,
                    allow_uninitialized=True,
                )
                self.runtime_version = str(result.get("userAgent") or "").split("/")[-1] or None
                await self.notify("initialized", {})
                self._initialized = True
            except Exception:
                await self.close()
                raise

    async def call(self, method: str, params: dict[str, Any] | None = None, *, timeout: float = 60, allow_uninitialized: bool = False) -> dict[str, Any]:
        if not allow_uninitialized and not self._initialized:
            await self.start()
        if not self._process or self._process.returncode is not None:
            raise CodexProcessError("Codex runtime is not running.")
        request_id = next(self._ids)
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
            try:
                return await asyncio.wait_for(future, timeout=timeout)
            except TimeoutError as exc:
                raise CodexRequestTimeout("Codex request timed out.") from exc
        finally:
            self._pending.pop(request_id, None)

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        if not self._process or self._process.returncode is not None:
            raise CodexProcessError("Codex runtime is not running.")
        await self._write({"jsonrpc": "2.0", "method": method, "params": params or {}})

    async def next_notification(self, *, timeout: float | None = None) -> tuple[str, dict[str, Any]]:
        if timeout is None:
            return await self._notification_queue.get()
        try:
            return await asyncio.wait_for(self._notification_queue.get(), timeout)
        except TimeoutError as exc:
            raise CodexRequestTimeout("Codex notification timed out.") from exc

    async def _write(self, message: dict[str, Any]) -> None:
        if not self._process or not self._process.stdin:
            raise CodexProcessError("Codex stdin is unavailable.")
        encoded = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
        if len(encoded) > self.MAX_LINE_BYTES:
            raise CodexProtocolError("Codex request exceeds the safe message limit.")
        async with self._write_lock:
            self._process.stdin.write(encoded)
            try:
                await self._process.stdin.drain()
            except (BrokenPipeError, ConnectionError) as exc:
                raise CodexProcessError("Codex connection closed.") from exc

    async def _read_stdout(self) -> None:
        assert self._process and self._process.stdout
        try:
            while True:
                try:
                    line = await self._process.stdout.readline()
                except ValueError:
                    self.last_error_code = "message_too_large"
                    return
                if not line:
                    return
                if len(line) > self.MAX_LINE_BYTES:
                    self.last_error_code = "message_too_large"
                    continue
                try:
                    message = json.loads(line)
                except (TypeError, json.JSONDecodeError):
                    self.last_error_code = "malformed_message"
                    continue
                if not isinstance(message, dict):
                    self.last_error_code = "malformed_message"
                    continue
                await self._dispatch(message)
        finally:
            self._fail_pending(CodexProcessError("Codex connection closed."))

    async def _dispatch(self, message: dict[str, Any]) -> None:
        if "id" in message and ("result" in message or "error" in message):
            request_id = message.get("id")
            if not isinstance(request_id, int):
                self.last_error_code = "invalid_response_id"
                return
            future = self._pending.get(request_id)
            if future is None or future.done():
                self.last_error_code = "unknown_response_id"
                return
            if "error" in message:
                future.set_exception(CodexProtocolError("Codex returned a protocol error."))
            else:
                result = message.get("result")
                future.set_result(result if isinstance(result, dict) else {})
            return
        method = message.get("method")
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        if not isinstance(method, str):
            self.last_error_code = "malformed_message"
            return
        if "id" in message:
            await self._handle_server_request(message.get("id"), method, params)
            return
        await self._notification_queue.put((method, params))
        if self._notification_handler:
            result = self._notification_handler(method, params)
            if asyncio.iscoroutine(result):
                await result

    async def _handle_server_request(self, request_id: Any, method: str, params: dict[str, Any]) -> None:
        response: dict[str, Any]
        try:
            if self._server_request_handler:
                result = self._server_request_handler(method, params)
                response = await result if asyncio.iscoroutine(result) else result
            else:
                response = {"error": {"code": -32601, "message": "Adele does not enable App Server tools."}}
        except Exception as exc:
            response = {"error": {"code": -32000, "message": safe_error_code(exc)}}
        response = {"jsonrpc": "2.0", "id": request_id, **response}
        await self._write(response)

    async def _drain_stderr(self) -> None:
        assert self._process and self._process.stderr
        while True:
            line = await self._process.stderr.readline()
            if not line:
                return
            # Stderr may include prompts or auth URLs. Keep only a classification.
            self.last_error_code = "runtime_stderr" if redact_text(line.decode("utf-8", "replace")).strip() else self.last_error_code

    async def _watch_process(self) -> None:
        assert self._process
        await self._process.wait()
        self._initialized = False
        self._fail_pending(CodexProcessError("Codex runtime exited."))

    def _fail_pending(self, error: CodexError) -> None:
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(error)

    async def close(self) -> None:
        self._initialized = False
        process = self._process
        self._process = None
        if process and process.returncode is None:
            try:
                if process.stdin:
                    process.stdin.close()
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=3)
                except TimeoutError:
                    process.kill()
        for task in (self._reader_task, self._stderr_task, self._wait_task):
            if task and task is not asyncio.current_task() and not task.done():
                task.cancel()
        self._fail_pending(CodexProcessError("Codex runtime shut down."))
