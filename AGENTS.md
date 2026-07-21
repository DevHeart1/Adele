# Adele repository guidance

## Layout and commands

- Desktop code is in `apps/desktop`; keep Web and landing changes out of desktop work.
- Run Desktop provider tests with `cd apps/desktop && .venv/Scripts/python.exe -m pytest tests/test_codex_app_server.py -q`.
- Regenerate App Server schemas with `codex app-server generate-json-schema --out apps/desktop/backend/providers/codex_schemas`.

## Build Week provider decision

- The active Desktop LLM path is ChatGPT sign-in through `codex app-server` and GPT-5.6 only.
- Adele never reads `auth.json`, browser cookies, passwords, API keys, or ChatGPT tokens.
- Keep Adele's tool registry, approval policies, and verification authority intact; App Server never executes desktop actions directly.
- Do not hand-edit generated schemas. Update protocol documentation and fake-server tests with any protocol change.
- Do not commit secrets, raw screenshots, personal data, or generated local environments.
