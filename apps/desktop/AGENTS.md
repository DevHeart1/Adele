# Adele Desktop guidance

- Use the provider abstraction in `backend/providers/base.py`; production composition is `CodexAppServerProvider` via `ModelRouter`.
- Use stdio with `asyncio.create_subprocess_exec` for Codex App Server. Do not expose it on a port or invoke a shell.
- Keep ChatGPT auth inside Codex. Renderer receives only sanitized connection state and a validated HTTPS login URL.
- Preserve approval and verification flows in `backend/agent` and `backend/tools`.
- Run `python -m pytest tests/test_codex_app_server.py -q` and targeted regressions before completing provider changes.
