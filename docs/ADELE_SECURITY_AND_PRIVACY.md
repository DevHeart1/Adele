# Adele security and privacy

- ChatGPT authentication, refresh, and logout are handled by Codex App Server. Adele does not read `~/.codex/auth.json`, cookies, passwords, access tokens, or refresh tokens.
- Auth URLs are opened only through a narrow Electron IPC handler that requires HTTPS and an OpenAI or ChatGPT host.
- Normal diagnostics retain only safe metadata such as provider, model, reasoning level, token counts, duration, tool names, and error category. Thread IDs are not exposed in renderer status.
- Raw prompts, responses, screenshots, screenshot paths, email contents, tool arguments with private data, and hidden reasoning text are not logged or shown in execution traces.
- Temporary screenshot files sent to Codex are deleted after turn completion, error, cancellation, or timeout.
- Adele's approval and verification systems remain authoritative for desktop or browser actions. A model response cannot bypass an approval gate.
