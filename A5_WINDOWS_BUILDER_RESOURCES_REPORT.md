# A5 Windows Builder Resource Paths Report

Date: 2026-06-17

Purpose: fix Windows installer resource paths and stale installer branding after the monorepo relocation.

Status: complete, with full installer build still deferred until runtime bundle generation.

## What Changed

Renamed NSIS build resources:

```text
apps/desktop/build/ciara-nsis-macros.nsh
-> apps/desktop/build/adele-nsis-macros.nsh

apps/desktop/build/ciara-nsis-installSection.nsh
-> apps/desktop/build/adele-nsis-installSection.nsh
```

Updated installer/build branding in:

```text
apps/desktop/build/adele-nsis-macros.nsh
apps/desktop/build/adele-nsis-installSection.nsh
apps/desktop/build/license.txt
apps/desktop/build/notarize.cjs
```

Updated desktop package scripts:

```json
{
  "install:app-deps": "electron-builder install-app-deps",
  "postinstall": "node scripts/apply-nsis-installsection.mjs"
}
```

Reason:

- The original `postinstall` ran `electron-builder install-app-deps && node scripts/apply-nsis-installsection.mjs`.
- In the workspace layout, `electron-builder install-app-deps` invokes a production npm install inside `apps/desktop`, which triggers `postinstall` again and can recurse.
- Splitting the scripts keeps the NSIS template patch automatic while making app-dependency installation explicit.

Added desktop builder config:

```yaml
electronVersion: 36.9.5
```

Reason:

- Electron is hoisted in the npm workspace.
- Electron Builder could not infer a fixed Electron version from `apps/desktop/node_modules`.
- The workspace lockfile resolves Electron to `36.9.5`.

## Resource Verification

Builder-referenced resources now exist:

```text
OK scripts/stamp-windows-icon.cjs
OK build/notarize.cjs
OK build/icon.ico
OK build/installerIcon.ico
OK build/installerSidebar.bmp
OK build/license.txt
OK build/adele-nsis-macros.nsh
OK build/icon.icns
OK build/entitlements.mac.plist
```

NSIS installSection patch:

```bash
npm --workspace apps/desktop run postinstall
```

Result:

```text
PASS
[apply-nsis-installsection] applied ADELE installSection -> node_modules/app-builder-lib/templates/nsis/installSection.nsh
```

Branding scan:

```bash
rg -n "CIARA|ciara|ciara-nsis|Control Intelligence" apps/desktop/build apps/desktop/electron-builder.yml apps/desktop/scripts
```

Result:

```text
PASS
No matches.
```

Electron Builder CLI:

```bash
npm --workspace apps/desktop exec electron-builder -- --version
```

Result:

```text
PASS
25.1.8
```

Electron runtime:

```bash
npm --workspace apps/desktop exec electron -- --version
```

Result:

```text
PASS
v36.9.5
```

Note:

- Because earlier workspace installs used `--ignore-scripts`, Electron needed:

```bash
npm rebuild electron
```

## Other Regression Checks

Branding script:

```bash
npm --workspace apps/desktop run branding
```

Result:

```text
PASS
```

Extension packaging:

```bash
npm run desktop:dist:extension
```

Result:

```text
PASS
```

Generated artifact cleanup:

```text
apps/desktop/dist removed after verification
```

Workspace test command:

```bash
npm run test
```

Result:

```text
PASS
```

## Deferred Full Installer Build

The full Windows installer build remains deferred.

Reason:

```text
apps/desktop/build/python/win-x64 is absent
apps/desktop/wheelhouse is absent
```

This is expected at this stage because the Windows build script owns runtime preparation:

```bash
npm run desktop:build:win
```

which delegates to:

```bash
npm run prepare:python:win
npm run prepare:wheelhouse:win
```

## A5 Completion Criteria

A5 is complete when:

```text
electron-builder.yml references existing NSIS include files
NSIS installSection source exists under the expected ADELE name
CIARA build branding is removed from installer resources
postinstall no longer recursively invokes install-app-deps
NSIS patch script runs successfully
Electron Builder CLI is available
Electron runtime is available
desktop extension packaging still works
full installer build blockers are documented separately
```

Status: complete.
