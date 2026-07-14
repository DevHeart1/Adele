# A2 Desktop And Landing Relocation Report

Date: 2026-06-17

Purpose: record the first physical monorepo relocation step. This step moved files only; it did not refactor paths, fix bugs, normalize docs, or create the root workspace package.

Status: complete.

## What Changed

Created:

```text
apps/
apps/desktop/
apps/landing/
```

Moved the existing desktop app into:

```text
apps/desktop/
```

Moved the existing landing app into:

```text
apps/landing/
```

## Desktop Move

Moved from repo root to `apps/desktop/`:

```text
main.js
preload.js
package.json
package-lock.json
electron-builder.yml
setup.sh
icon.png
renderer/
backend/
chrome_extension/
build/
scripts/
tests/
benchmarks/
experiments/
CONTRIBUTING.md
```

Verified present after move:

```text
apps/desktop/main.js
apps/desktop/preload.js
apps/desktop/package.json
apps/desktop/backend/servers/local_server.py
apps/desktop/renderer/index.html
apps/desktop/chrome_extension/manifest.json
apps/desktop/electron-builder.yml
apps/desktop/setup.sh
apps/desktop/build/
apps/desktop/scripts/
apps/desktop/tests/
```

Validation:

```text
apps/desktop/package.json parses successfully
```

## Landing Move

Moved from:

```text
landing/
```

To:

```text
apps/landing/
```

Verified present after move:

```text
apps/landing/package.json
apps/landing/package-lock.json
apps/landing/vite.config.js
apps/landing/src/
apps/landing/public/
apps/landing/assets/
apps/landing/vercel.json
```

Validation:

```text
apps/landing/package.json parses successfully
```

## Root Files Retained

Still at repo root:

```text
.git/
.venv/
adele-docs/
.dockerignore
.gitignore
LICENSE
README.md
IMPLEMENTATION_PLAN.md
A0_BASELINE_AUDIT.md
A1_MONOREPO_LAYOUT.md
A2_RELOCATION_REPORT.md
```

## Temporary State Before A3

The root no longer has:

```text
package.json
package-lock.json
main.js
preload.js
electron-builder.yml
setup.sh
```

This is expected after A2.

A3 must create the root workspace `package.json` and root workspace lockfile strategy.

## Git Status Shape

Git currently sees many deleted root paths and one new untracked `apps/` tree.

This is expected because files were moved but not committed. Git will recognize many of these as renames once staged or viewed with rename detection.

## No Intentional Fixes Yet

A2 did not fix the known baseline issues:

```text
apps/desktop/backend/agent/memory.py syntax error remains
apps/desktop/electron-builder.yml still references missing build/adele-nsis-macros.nsh
apps/desktop/build still contains CIARA-branded files
adele-docs has not yet been normalized to docs
root workspace package.json has not yet been created
```

Those belong to later Track A milestones.

## A2 Completion Criteria

A2 is complete when:

```text
apps/desktop exists
apps/landing exists
desktop files are under apps/desktop
landing files are under apps/landing
expected files parse or exist in new locations
no refactor/fix work has been mixed into the relocation
```

Status: complete.
