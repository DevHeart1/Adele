# A3 Workspace Setup Report

Date: 2026-06-17

Purpose: convert the repository root into an npm workspace orchestrator after the A2 relocation.

Status: complete, with one desktop path issue deferred to A4.

## What Changed

Created root workspace package:

```text
package.json
```

Generated root workspace lockfile:

```text
package-lock.json
```

Installed workspace dependencies from the root with lifecycle scripts skipped:

```bash
npm install --ignore-scripts
```

Reason lifecycle scripts were skipped:

- The first plain `npm install` exceeded the tool timeout before producing a lockfile.
- Desktop `postinstall` runs Electron-builder app-dependency work and NSIS patching, which is heavier than needed for A3 workspace wiring.
- A3's goal is workspace setup, not desktop packaging validation.

## Root Workspace Package

Root package identity:

```json
{
  "name": "adele-monorepo",
  "private": true,
  "version": "1.0.0"
}
```

Workspace globs:

```json
[
  "apps/*",
  "packages/*"
]
```

Root scripts now available:

```text
desktop:start
desktop:build:win
desktop:build:win:portable
desktop:build:mac
desktop:dist:extension
landing:dev
landing:build
landing:preview
web:dev
web:build
web:start
web-extension:build
test
build
```

Current root `build` script:

```bash
npm run landing:build
```

Reason:

- `apps/web` and `apps/web-extension` do not exist until Track B.
- Desktop installer builds are platform/heavy and remain explicit commands.

## Workspace Lockfile

Root lockfile was created and parsed successfully.

Validation:

```text
package-lock.json name: adele-monorepo
lockfileVersion: 3
contains apps/desktop: true
contains apps/landing: true
```

Workspace symlinks/junctions created:

```text
node_modules/adele         -> apps/desktop
node_modules/adele-landing -> apps/landing
```

## Workspace Package Validation

Desktop workspace scripts are visible:

```bash
npm --workspace apps/desktop run
```

Landing workspace scripts are visible:

```bash
npm --workspace apps/landing run
```

Root scripts are visible:

```bash
npm run
```

Root test command:

```bash
npm run test
```

Result:

```text
PASS
```

Note:

- No workspace currently defines a JS `test` script, so this is a clean no-op.

Landing build:

```bash
npm run landing:build
```

Result:

```text
PASS
```

The generated `apps/landing/dist` verification output was removed after the check.

## Deferred A4 Issue

Desktop extension packaging command:

```bash
npm run desktop:dist:extension
```

Result:

```text
FAIL
```

Failure:

```text
Error: ENOENT: no such file or directory, mkdir 'C:\C:\Users\USER\Documents\Adele\apps\desktop\dist\adele-browser-bridge'
```

Cause:

- `apps/desktop/scripts/package-extension.mjs` derives `ROOT` using `new URL("..", import.meta.url).pathname`.
- On Windows this produces a pathname style that later becomes malformed as `C:\C:\...`.

Disposition:

- This is a desktop path assumption issue.
- It belongs to A4: Fix Desktop Path Assumptions.
- No fix was applied during A3 to keep A3 focused on workspace setup.

## Dependency Audit Baseline After Workspace Install

Command:

```bash
npm audit --omit=dev --json
```

Result:

```text
2 high severity vulnerabilities
```

Reported packages:

```text
vite
esbuild
```

Note:

- The full install reported 12 high severity vulnerabilities when dev dependencies were included.
- Dependency remediation is not part of A3.

## Current Lockfile Transition State

Current lockfiles:

```text
package-lock.json
apps/desktop/package-lock.json
apps/landing/package-lock.json
```

Target final state:

```text
package-lock.json
```

Disposition:

- Nested lockfiles remain for now.
- Removing nested lockfiles should happen after workspace install and app commands are fully stable.

## A3 Completion Criteria

A3 is complete when:

```text
root package.json exists as workspace orchestrator
root package-lock.json exists
apps/desktop is recognized as a workspace
apps/landing is recognized as a workspace
root scripts are available
landing build works through root workspace command
test command works as a workspace no-op
desktop path issues are identified for A4
```

Status: complete.
