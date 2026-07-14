# A8 Python Test Environment Report

Date: 2026-06-17

## Goal

Rebuild the desktop Python/test environment from the new monorepo location so backend imports and targeted tests run from `apps/desktop`.

## Environment Decision

Created an isolated desktop development virtual environment at:

```text
apps/desktop/.venv
```

This keeps developer/test dependencies local to the desktop app while leaving the Electron runtime bootstrap behavior intact.

## Changes Made

### 1. Added dev requirements

Created:

```text
apps/desktop/backend/requirements-dev.txt
```

It includes the backend runtime requirements plus:

```text
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

### 2. Ignored local virtual environments

Updated `.gitignore` to ignore:

```text
.venv/
```

### 3. Updated developer setup docs

Updated:

```text
README.md
docs/desktop/GUIDE.md
```

The docs now use the desktop-local environment:

```powershell
cd apps\desktop
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
```

### 4. Updated desktop shell setup default

Updated:

```text
apps/desktop/setup.sh
```

Manual developer setup now defaults to:

```text
apps/desktop/.venv
```

`ADELE_VENV_DIR` still overrides this path, so Electron can continue passing a runtime-specific venv path when needed.

### 5. Updated legacy test helper

Updated:

```text
apps/desktop/tests/run_test.sh
```

It now activates `../.venv` from the `tests/` directory instead of the old `venv` path.

### 6. Fixed live Gemini test collection

Updated:

```text
apps/desktop/tests/test_agent_schema.py
```

The test previously executed at import/collection time and failed immediately without a Gemini API key. It is now a proper `pytest` async test and skips when neither `GEMINI_API_KEY` nor `GOOGLE_API_KEY` is configured.

## Commands Run

Created the venv:

```powershell
cd apps\desktop
python -m venv .venv
```

Installed pip tooling:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
```

Installed backend/test requirements:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
```

## Verification

### Dependency check

```powershell
.\.venv\Scripts\python.exe -m pip check
```

Result:

```text
No broken requirements found.
```

### Backend compile check

```powershell
.\.venv\Scripts\python.exe -m py_compile backend\agent\memory.py backend\servers\local_server.py backend\agent\core_v2.py
```

Result:

```text
Pass
```

### Backend import smoke check

From `apps/desktop/backend`:

```powershell
..\.venv\Scripts\python.exe -c "import agent.memory, agent.core_v2, servers.local_server; print('desktop backend imports ok')"
```

Result:

```text
desktop backend imports ok
```

### Targeted pytest

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_gemini_provider.py tests\test_agent_schema.py
```

Result:

```text
5 passed, 1 skipped
```

The skipped test is the live Gemini schema test because no Gemini API key is configured in the local environment.

## Current State

A8 is complete.

The desktop Python environment is rebuilt under `apps/desktop/.venv`, backend imports work, dependency resolution is clean, and the targeted test pair runs.

## Known Follow-Ups

- A9 should run broader desktop regression tests from the new environment.
- Live Gemini tests require `GEMINI_API_KEY` or `GOOGLE_API_KEY`.
- Electron runtime still creates/uses its own runtime venv path through `main.js`; this was intentionally left unchanged in A8.
