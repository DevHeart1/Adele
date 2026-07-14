# Build Week Desktop setup

1. Install the Codex desktop app or CLI and confirm `codex --version` works. Adele also supports `ADELE_CODEX_EXECUTABLE` for a developer-only executable override.
2. Install Desktop dependencies, then start Adele with `npm run desktop:start` from the repository root.
3. In Adele, choose **Continue with ChatGPT**. The sign-in page opens in the default browser; Adele does not embed it or receive credentials.
4. After the connection check shows **Connected with ChatGPT**, confirm the displayed model is **GPT-5.6**.
5. Grant only the microphone and screen permissions needed for your demo. Install the browser extension from Adele's onboarding flow when browser automation is required.

If Codex is missing, install it and restart Adele. If GPT-5.6 is unavailable for the signed-in account, Adele will not silently fall back to another model.

## Test commands

```powershell
cd apps/desktop
.venv/Scripts/python.exe -m pytest tests/test_codex_app_server.py -q
```

The fake App Server test does not require network access or a personal ChatGPT account.
