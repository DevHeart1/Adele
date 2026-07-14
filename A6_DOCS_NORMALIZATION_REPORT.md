# A6 Docs Normalization Report

Date: 2026-06-17

## Goal

Normalize ADELE documentation for the monorepo layout by moving the old documentation asset folder to the canonical `docs/` path, repairing stale README links, and adding the minimum guide structure needed for desktop, web, architecture, and hackathon submission planning.

## Changes Made

### 1. Canonical docs folder

Moved the old documentation asset folder:

```text
adele-docs/ -> docs/
```

The canonical documentation tree is now:

```text
docs/
  README.md
  architecture/
    README.md
  desktop/
    GUIDE.md
  diagrams/
  screenshots/
  submission/
    HACKATHON_SUBMISSION.md
  web/
    README.md
```

### 2. Git ignore rule fixed

Removed the local-only ignore rule for `docs/` from `.gitignore`.

This makes the documentation tree trackable as a first-class repo artifact.

### 3. Root README replaced

Replaced the old single-package desktop README with a monorepo-aware README that now documents:

- ADELE Desktop as the existing Electron and Python product under `apps/desktop`.
- ADELE Web as the planned web companion and cloud memory vault.
- ADELE Web extension as a planned separate extension under `apps/web-extension`.
- Existing landing site under `apps/landing`.
- Root workspace commands such as `npm run desktop:start`, `npm run landing:dev`, and `npm run desktop:dist:extension`.
- Current docs links under the normalized `docs/` tree.

The README still preserves existing visual assets under `docs/screenshots`.

### 4. New documentation entry points

Created focused documentation entry points:

```text
docs/README.md
docs/desktop/GUIDE.md
docs/web/README.md
docs/architecture/README.md
docs/submission/HACKATHON_SUBMISSION.md
```

These files are intentionally concise reference pages for the current monorepo stage. They can be expanded during Track B when the web app, web extension, shared packages, auth, and cloud memory vault become implementation work.

## Verification

### Local markdown links

Ran a PowerShell markdown link check across project Markdown files outside `.git`, `node_modules`, and `.venv`.

Result:

```text
All project Markdown local links resolved.
```

### Stale docs references

Searched for stale active references:

```powershell
rg -n "adele-docs|docs/GUIDE.md|docs/HACKATHON_SUBMISSION.md" -g "*.md" -g "*.json" -g "*.yml" -g "*.yaml"
```

Result:

- No stale references remain in the active root README or new docs tree, except this report's own record of the completed move.
- Remaining hits are historical milestone reports and the implementation plan documenting the pre-A6 state and planned A6 work.

### Installer branding regression check

Searched active desktop builder resources and docs for stale CIARA branding:

```powershell
rg -n "CIARA|ciara|Control Intelligence" apps/desktop/build apps/desktop/electron-builder.yml apps/desktop/scripts README.md docs -g "!node_modules"
```

Result:

```text
No matches.
```

## Current State

A6 is complete.

The repository now has a stable documentation home at `docs/`, and the root README describes the monorepo direction instead of the old root-level desktop layout.

## Known Follow-Ups

- `apps/desktop/CONTRIBUTING.md` still reflects the desktop app's older product wording and should either be refreshed or replaced with a pointer to `docs/desktop/GUIDE.md`.
- Historical milestone reports intentionally keep old terms such as `adele-docs` and `ciara` because they document previous repo state.
- A7 should move into backend/runtime correctness, including the known syntax issue in `apps/desktop/backend/agent/memory.py`.
