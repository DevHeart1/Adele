---
name: adele-codex-app-server
description: Implement, debug, test, or review Adele Desktop's Codex App Server integration, ChatGPT sign-in flow, GPT-5.6 provider, model discovery, streaming, structured tools, approvals, and safe telemetry. Use for changes under apps/desktop that affect Codex authentication or inference. Do not use for unrelated landing-page or Adele Web work.
---

# Adele Codex App Server workflow

1. Read the applicable `AGENTS.md` files and inspect `apps/desktop/backend/providers/codex_schemas` before changing protocol code.
2. Verify protocol-sensitive changes against the generated schema and official OpenAI documentation. Regenerate schemas with the documented command when the Codex CLI version changes.
3. Keep one stdio App Server process per backend and one shared provider instance. Never read or store `auth.json`, tokens, cookies, or passwords.
4. Require a ChatGPT account and select only `gpt-5.6`, with `gpt-5.6-sol` only when the catalog explicitly advertises it as the available variant.
5. Keep dynamic tools disabled unless their calls are validated through Adele's registry, approval policy, and verification path.
6. Run the fake App Server tests, targeted provider tests, and relevant Desktop regressions. Check diffs and logs for token, URL, prompt, screenshot, and path leakage.
7. Report the Codex CLI version, model/auth assumptions, and any interactive sign-in or packaging checks that remain manual.
