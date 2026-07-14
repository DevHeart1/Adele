# A0 Baseline Audit And Freeze

Date: 2026-06-17

Purpose: capture the current state of Adele before any monorepo migration, file movement, path rewrites, or implementation work. This baseline separates pre-existing issues from issues introduced during Track A.

## Current Repository Shape

Root: `C:\Users\USER\Documents\Adele`

Top-level directories:

```text
.git
.venv
adele-docs
backend
benchmarks
build
chrome_extension
experiments
landing
renderer
scripts
tests
```

Top-level desktop app files:

```text
main.js
preload.js
package.json
package-lock.json
electron-builder.yml
setup.sh
icon.png
README.md
CONTRIBUTING.md
LICENSE
IMPLEMENTATION_PLAN.md
```

Approximate source inventory, excluding lockfiles and `node_modules`:

```text
All tracked/discovered source-ish files: 291
Backend Python files: 77
Test Python/JS files: 41
Chrome extension JS/HTML/JSON files: 8
Renderer JS/HTML/CSS files: 3
```

## Git Baseline

Current `git status --short`:

```text
?? IMPLEMENTATION_PLAN.md
```

Notes:

- The only untracked file is the implementation plan created before A0.
- No migration files have been moved yet.

## Runtime Baseline

Detected local tooling:

```text
Python 3.13.7
Node v22.19.0
npm 10.9.3
```

Virtual environment status:

```text
.venv directory exists
.venv\Scripts\python.exe is missing
```

Implication:

- Python tests cannot currently run from the checked-in `.venv`.
- A8 should rebuild the Python/test environment after the desktop app is relocated.

## Current Root `package.json`

Package identity:

```json
{
  "name": "adele",
  "productName": "ADELE",
  "version": "1.0.0",
  "description": "ADELE - Memory-aware desktop companion",
  "author": "Startrz Technologies",
  "main": "main.js"
}
```

Current npm scripts:

```text
start                 electron .
branding              node scripts/generate-branding.mjs
prepare:python:win    powershell -ExecutionPolicy Bypass -File scripts/prepare-python-runtime.ps1
prepare:wheelhouse:win powershell -ExecutionPolicy Bypass -File scripts/prepare-wheelhouse.ps1
prepare:runtime:win   npm run prepare:python:win && npm run prepare:wheelhouse:win
build                 electron-builder --mac
build:mac             electron-builder --mac
build:win             npm run branding && npm run prepare:runtime:win && cross-env CSC_IDENTITY_AUTO_DISCOVERY=false electron-builder --win --x64 --publish never
build:win:portable    npm run branding && npm run prepare:runtime:win && cross-env CSC_IDENTITY_AUTO_DISCOVERY=false electron-builder --win portable --x64 --publish never
build:dmg             electron-builder --mac dmg
build:dir             electron-builder --mac dir
build:signed          electron-builder --mac --universal
release               electron-builder --mac --universal --publish never
publish:win           npm run branding && cross-env CSC_IDENTITY_AUTO_DISCOVERY=false electron-builder --win --x64 --publish always
publish:mac           electron-builder --mac --universal --publish always
dist:extension        node scripts/package-extension.mjs
postinstall           electron-builder install-app-deps && node scripts/apply-nsis-installsection.mjs
```

Dependencies:

```text
electron-updater
katex
node-global-key-listener
ws
```

Dev dependencies:

```text
cross-env
electron
electron-builder
png-to-ico
resedit
sharp
```

Validation:

```text
package.json parses successfully
```

## Electron Build Baseline

Current build config: `electron-builder.yml`

Important current assumptions:

```text
buildResources: build
output: release
main process file: main.js
preload file: preload.js
renderer path: renderer/**/*
backend extraResource: backend -> backend
setup script extraResource: setup.sh -> setup.sh
Windows PTT script: scripts/win-alt-ptt.ps1
Chrome extension extraResource: chrome_extension -> chrome_extension
Windows artifact: ADELE-Setup-${version}.${ext}
NSIS include: build/adele-nsis-macros.nsh
```

Pre-existing packaging issue:

```text
build/adele-nsis-macros.nsh does not exist
build/ciara-nsis-macros.nsh exists
```

Also present:

```text
build/ciara-nsis-installSection.nsh
build/license.txt contains CIARA branding
build/notarize.cjs references CIARA
```

Implication:

- A5 must correct Windows builder resource paths and stale CIARA branding.
- This is a pre-existing issue, not caused by the monorepo migration.

## Electron/Main Process Path Assumptions

Current `main.js` important path assumptions:

```text
APP_ROOT = process.resourcesPath when packaged, otherwise __dirname
BACKEND_ROOT = APP_ROOT/backend when packaged, otherwise __dirname/backend
getVenvRoot() = userData/venv when packaged, otherwise __dirname/venv
setup.sh = APP_ROOT/setup.sh when packaged, otherwise __dirname/setup.sh
Python backend entrypoint = BACKEND_ROOT/servers/local_server.py
renderer entrypoint = __dirname/renderer/index.html
Chrome extension source = APP_ROOT/chrome_extension when packaged, otherwise __dirname/chrome_extension
Windows PTT script lookup includes APP_ROOT/scripts/win-alt-ptt.ps1 and __dirname/scripts/win-alt-ptt.ps1
```

Implication:

- A4 must update path assumptions after moving desktop files into `apps/desktop`.

## Backend Baseline

Primary backend entrypoint:

```text
backend/servers/local_server.py
```

Agent entrypoint:

```text
backend/agent/__init__.py
backend/agent/core_v2.py
```

Provider defaults:

```text
backend/providers/gemini.py DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"
main.js DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"
renderer/renderer.js DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"
```

Compile checks:

```text
python -m py_compile backend/servers/local_server.py
PASS

python -m py_compile backend/agent/memory.py
FAIL
```

Pre-existing backend blocker:

```text
File "backend\agent\memory.py", line 27
  from pymongo import MongoClient as _PymongoMongoClient
  ^^^^
SyntaxError: expected 'except' or 'finally' block
```

Implication:

- A7 must fix `backend/agent/memory.py` after relocation.
- This is a pre-existing issue, not caused by the monorepo migration.

## Chrome Extension Baseline

Current extension path:

```text
chrome_extension/
```

Important files:

```text
chrome_extension/manifest.json
chrome_extension/background.js
chrome_extension/content_script.js
chrome_extension/options.js
chrome_extension/popup.js
chrome_extension/Readability.js
```

Current local bridge defaults:

```text
DEFAULT_BRIDGE_URL = "ws://127.0.0.1:8765"
DEFAULT_BRIDGE_TOKEN = "dev-bridge-token"
```

Backend browser bridge default:

```text
backend/browser/bridge.py uses configured ADELE_BROWSER_BRIDGE_TOKEN or "dev-bridge-token"
```

Implication:

- This is acceptable as a baseline but should be treated as a product security issue later.
- The desktop migration must preserve the current extension export/bridge behavior first.

## Docs Baseline

Current docs directory:

```text
adele-docs/
```

Missing expected docs directory:

```text
docs/ does not exist
```

README currently references paths like:

```text
docs/screenshots/...
docs/GUIDE.md
docs/HACKATHON_SUBMISSION.md
```

Pre-existing docs mismatch:

```text
README points at docs/... but repo uses adele-docs/...
```

Additional docs issue:

```text
CONTRIBUTING.md contains mojibake/encoding corruption in headings and diagrams.
```

Implication:

- A6 should normalize `adele-docs` to `docs` and repair README/doc references.

## Security And Dependency Baseline

Root app production audit:

```text
npm audit --omit=dev
2 vulnerabilities total
1 high
1 moderate
```

Root app advisories:

```text
ws: high/moderate advisories affecting installed 8.x range below fixed versions
js-yaml: moderate advisory
```

Landing app production audit:

```text
landing/npm audit --omit=dev
3 vulnerabilities total
2 high
1 low
```

Landing app advisories:

```text
vite: high/moderate advisories
esbuild: high/low advisories
@babel/core: low advisory
```

Other security-relevant baseline notes:

```text
Hardcoded Picovoice key exists in main.js and renderer/renderer.js
Browser bridge default token is dev-bridge-token
Chrome extension has broad host_permissions: <all_urls>
Desktop app exposes powerful local tools: shell, file I/O, browser actions, desktop automation
```

Implication:

- Dependency/security fixes are known work items.
- Track A should preserve behavior first; security hardening should be scheduled after migration unless it blocks builds.

## Pre-Existing Known Issues List

These existed before Track A migration:

1. `backend/agent/memory.py` syntax error blocks compile/import.
2. `.venv\Scripts\python.exe` is missing despite `.venv` directory existing.
3. `electron-builder.yml` references missing `build/adele-nsis-macros.nsh`.
4. Build resources still contain CIARA names/content.
5. README references `docs/...`, but repo contains `adele-docs/...`.
6. `CONTRIBUTING.md` has encoding corruption/mojibake.
7. Root npm audit reports vulnerable `ws` and `js-yaml`.
8. Landing npm audit reports vulnerable `vite`, `esbuild`, and `@babel/core`.
9. Browser bridge default token is `dev-bridge-token`.
10. Bundled Picovoice key is hardcoded in desktop main and renderer code.
11. README/product copy says Gemma 4 while implementation defaults to `gemini-3-flash-preview`.

## A0 Completion Criteria

A0 is complete when:

- Current repo shape is documented.
- Current scripts and build assumptions are documented.
- Current backend/extension/docs paths are documented.
- Current test/build baseline is documented.
- Pre-existing blockers are clearly separated from future migration issues.

Status: complete.
