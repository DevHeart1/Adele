# A4 Desktop Path Fixes Report

Date: 2026-06-17

Purpose: fix desktop path assumptions exposed by the A2/A3 monorepo relocation while avoiding unrelated product refactors.

Status: complete.

## What Changed

Patched:

```text
apps/desktop/scripts/package-extension.mjs
```

Reason:

- After moving the desktop app to `apps/desktop`, `npm run desktop:dist:extension` failed on Windows with a malformed path:

```text
C:\C:\Users\USER\Documents\Adele\apps\desktop\dist\adele-browser-bridge
```

Root cause:

- The script used `new URL("..", import.meta.url).pathname`, which is not a safe filesystem path on Windows.
- The script also used Unix-only shell commands:
  - `rm`
  - `zip`
  - `stat -f`

## Patch Summary

Changed path derivation from URL pathname parsing to Node's filesystem-safe helpers:

```js
fileURLToPath(import.meta.url)
dirname(...)
```

Changed cleanup and file size operations from shell commands to Node APIs:

```js
rmSync(...)
statSync(...)
```

Changed archive creation to be platform-aware:

```text
Windows: PowerShell Compress-Archive
Other platforms: zip CLI from the dist cwd
```

## Verification Commands

Syntax checks:

```bash
node --check apps/desktop/scripts/package-extension.mjs
node --check apps/desktop/main.js
node --check apps/desktop/preload.js
```

Result:

```text
PASS
```

Electron binary check:

```bash
npm --workspace apps/desktop exec electron -- --version
```

Result:

```text
PASS
v36.9.5
```

Note:

- This required:

```bash
npm rebuild electron --workspace apps/desktop
```

- Reason: A3 used `npm install --ignore-scripts`, so Electron's package install script had not downloaded/installed its binary yet.

Desktop extension packaging:

```bash
npm run desktop:dist:extension
```

Result:

```text
PASS
Created apps/desktop/dist/adele-browser-bridge.zip
Size: 69 KB
```

Generated artifact cleanup:

```text
apps/desktop/dist removed after verification
```

Landing regression check:

```bash
npm run landing:build
```

Result:

```text
PASS
```

Generated artifact cleanup:

```text
apps/landing/dist removed after verification
```

Workspace test command:

```bash
npm run test
```

Result:

```text
PASS
```

Note:

- This is currently a clean workspace no-op because no workspace has a JS `test` script.

## A4 Scope Notes

A4 did not fix:

```text
apps/desktop/electron-builder.yml missing build/adele-nsis-macros.nsh
apps/desktop/build CIARA branding
apps/desktop/scripts/apply-nsis-installsection.mjs missing adele-nsis-installSection.nsh
apps/desktop/backend/agent/memory.py syntax error
adele-docs -> docs normalization
```

Those belong to later milestones:

```text
A5: Windows builder resource paths and NSIS branding/files
A6: Docs normalization
A7: Desktop backend import/startup blockers
```

## A4 Completion Criteria

A4 is complete when:

```text
workspace-broken desktop path script is patched
desktop extension packaging works from root workspace command
Electron package binary is usable again after A3's ignore-scripts install
syntax checks pass for patched desktop JS files
generated verification artifacts are cleaned up
unrelated known issues are left for their planned milestones
```

Status: complete.
