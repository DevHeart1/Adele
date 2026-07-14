# ADELE Desktop Guide

ADELE Desktop is the current Electron + Python local assistant. It provides the overlay UI, voice/text entry, local Python backend, desktop automation tools, and local Chrome extension bridge.

## Location

```text
apps/desktop/
```

## Start From Repo Root

```bash
npm run desktop:start
```

## Important Paths

```text
apps/desktop/main.js                    Electron main process
apps/desktop/preload.js                 IPC bridge
apps/desktop/renderer/                  Overlay UI
apps/desktop/backend/                   Python backend
apps/desktop/chrome_extension/          Desktop browser bridge extension
apps/desktop/electron-builder.yml       Desktop packaging config
apps/desktop/build/                     Installer and icon resources
```

## Python Backend

The main backend entrypoint is:

```text
apps/desktop/backend/servers/local_server.py
```

The app stores runtime data under `ADELE_DATA_DIR` when set, otherwise the backend resolves a local ADELE data directory through `runtime_paths.py`.

For development and tests, use the desktop-local virtual environment:

```powershell
cd apps\desktop
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
```

Then run targeted tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_gemini_provider.py tests\test_agent_schema.py
```

## Desktop Extension

Package the desktop Chrome extension from the repo root:

```bash
npm run desktop:dist:extension
```

The extension source lives at:

```text
apps/desktop/chrome_extension/
```

## Build Notes

Windows installer:

```bash
npm run desktop:build:win
```

macOS build:

```bash
npm run desktop:build:mac
```

The Windows build prepares bundled Python runtime and wheelhouse resources before invoking Electron Builder.

## Known Follow-Up

Track A still includes broader desktop regression testing in later milestones.
