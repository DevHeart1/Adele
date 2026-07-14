# A1 Monorepo Layout Contract

Date: 2026-06-17

Purpose: define the target monorepo structure, workspace strategy, package boundaries, command names, and migration rules before any desktop files are moved.

Status: complete.

## Decision Summary

Adele will become an npm-workspace monorepo with separate apps for desktop, web, web extension, and landing, plus shared packages for schemas, agent contracts, browser automation contracts, and connector abstractions.

Use **npm workspaces** first. This keeps disruption low because the current repo already uses npm and `package-lock.json`.

## Target Repository Layout

```text
Adele/
  apps/
    desktop/
      main.js
      preload.js
      package.json
      package-lock.json              # removed later if root lockfile fully owns workspace
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
      CONTRIBUTING.md                # later moved/converted into docs/desktop

    web/
      package.json
      next.config.*
      src/
      public/
      .env.example

    web-extension/
      package.json
      manifest.json
      src/
      public/

    landing/
      package.json
      src/
      public/
      vite.config.js
      vercel.json

  packages/
    shared/
      package.json
      src/

    agent-core/
      package.json
      src/

    browser-automation/
      package.json
      src/

    connectors/
      package.json
      src/

  infra/
    aws/
      dynamodb/
      README.md

  docs/
    architecture/
    desktop/
    web/
    submission/
    screenshots/
    diagrams/

  package.json
  package-lock.json
  README.md
  LICENSE
  .gitignore
  .dockerignore
  IMPLEMENTATION_PLAN.md
  A0_BASELINE_AUDIT.md
  A1_MONOREPO_LAYOUT.md
```

## Workspace Strategy

Root `package.json` becomes the workspace orchestrator.

Target root package:

```json
{
  "name": "adele-monorepo",
  "private": true,
  "workspaces": [
    "apps/*",
    "packages/*"
  ],
  "scripts": {
    "desktop:start": "npm --workspace apps/desktop start",
    "desktop:build:win": "npm --workspace apps/desktop run build:win",
    "desktop:build:win:portable": "npm --workspace apps/desktop run build:win:portable",
    "desktop:build:mac": "npm --workspace apps/desktop run build:mac",
    "desktop:dist:extension": "npm --workspace apps/desktop run dist:extension",
    "web:dev": "npm --workspace apps/web run dev",
    "web:build": "npm --workspace apps/web run build",
    "web:start": "npm --workspace apps/web run start",
    "web-extension:build": "npm --workspace apps/web-extension run build",
    "landing:dev": "npm --workspace apps/landing run dev",
    "landing:build": "npm --workspace apps/landing run build",
    "test": "npm --workspaces run test --if-present",
    "build": "npm run web:build && npm run web-extension:build && npm run landing:build"
  }
}
```

Notes:

- Root `build` intentionally does not build the desktop installer by default because desktop packaging is heavier and platform-specific.
- Desktop installer commands remain explicit.
- The current `landing/` app should move to `apps/landing` instead of being left at root.

## Package Boundaries

### `apps/desktop`

Owns the existing Electron app.

Includes:

```text
Electron main/preload
Renderer overlay UI
Python backend
Desktop Chrome extension
Desktop build resources
Desktop packaging scripts
Desktop tests/benchmarks/experiments for now
```

Migration rule:

- A2 should relocate files only.
- Do not refactor desktop internals during the move.
- Do not fix unrelated product/security issues during the pure relocation step unless required to keep the app startable.

### `apps/web`

Owns Adele Web.

Responsibilities:

```text
Next.js app
Cloud memory vault
Task timeline
Approval queue
Connector/MCP management UI
Browser session UI
Vercel deployment target
```

Created in Track B, not Track A.

### `apps/web-extension`

Owns Adele Web's Chrome extension.

Responsibilities:

```text
Extension pairing with Adele Web
Active tab snapshots
DOM element refs
Browser click/type/select/scroll actions
Action result reporting
```

Created in Track B, not Track A.

### `apps/landing`

Owns the existing Vite landing site.

Current source:

```text
landing/
```

Migration target:

```text
apps/landing/
```

This should happen during Track A so the root is clean.

### `packages/shared`

Owns cross-surface schemas and types.

Initial contracts:

```text
MemoryEntry
TaskRun
TaskStep
Plan
Milestone
ApprovalRequest
BrowserSnapshot
BrowserElementRef
BrowserAction
BrowserActionResult
ConnectorConfig
ToolCall
UserPreference
```

Created in Track B after the workspace exists.

### `packages/agent-core`

Owns shared agent concepts over time.

Initial contents should be small:

```text
Prompt fragments
Planning types
Tool selection contracts
Verification status contracts
```

Do not try to port the Python agent into TypeScript immediately.

### `packages/browser-automation`

Owns browser automation protocol shared by desktop extension and web extension.

Initial contents:

```text
Snapshot schema
Element ref schema
Action schema
Action result schema
Protocol constants
```

### `packages/connectors`

Owns connector abstractions.

Providers:

```text
Composio
HTTP MCP
future local bridge MCP
native API adapters
```

## Documentation Strategy

Current:

```text
adele-docs/
README.md references docs/...
CONTRIBUTING.md has encoding issues
```

Target:

```text
docs/
  architecture/
  desktop/
  web/
  submission/
  screenshots/
  diagrams/
```

Rules:

- Move `adele-docs` to `docs` during A6.
- Convert `CONTRIBUTING.md` into a readable `docs/desktop/DEVELOPER_GUIDE.md` or rewrite it.
- Root `README.md` becomes a monorepo overview, not desktop-only documentation.

## Lockfile Strategy

Preferred:

```text
one root package-lock.json
```

Transition:

1. Move current root `package.json` to `apps/desktop/package.json`.
2. Move current `landing/package.json` to `apps/landing/package.json`.
3. Create root workspace `package.json`.
4. Run `npm install` from root.
5. Let root `package-lock.json` become the workspace lockfile.
6. Remove nested lockfiles later only after workspace install is verified.

Current nested lockfiles:

```text
package-lock.json
landing/package-lock.json
```

Target:

```text
package-lock.json
```

## A2 Move Map

Move current root desktop app files into `apps/desktop`:

```text
main.js                         -> apps/desktop/main.js
preload.js                      -> apps/desktop/preload.js
package.json                    -> apps/desktop/package.json
package-lock.json               -> temporarily apps/desktop/package-lock.json or preserved until A3
electron-builder.yml            -> apps/desktop/electron-builder.yml
setup.sh                        -> apps/desktop/setup.sh
icon.png                        -> apps/desktop/icon.png
renderer/                       -> apps/desktop/renderer/
backend/                        -> apps/desktop/backend/
chrome_extension/               -> apps/desktop/chrome_extension/
build/                          -> apps/desktop/build/
scripts/                        -> apps/desktop/scripts/
tests/                          -> apps/desktop/tests/
benchmarks/                     -> apps/desktop/benchmarks/
experiments/                    -> apps/desktop/experiments/
CONTRIBUTING.md                 -> apps/desktop/CONTRIBUTING.md
```

Move current landing app:

```text
landing/                        -> apps/landing/
```

Keep at root:

```text
.git/
.gitignore
.dockerignore
LICENSE
README.md
IMPLEMENTATION_PLAN.md
A0_BASELINE_AUDIT.md
A1_MONOREPO_LAYOUT.md
adele-docs/                     # until A6 docs normalization
```

Create at root:

```text
apps/
packages/
infra/
docs/                           # later in A6
package.json                    # workspace root in A3
package-lock.json               # workspace lockfile in A3
```

## A3 Root Script Contract

After A3, these commands should exist from repo root:

```bash
npm run desktop:start
npm run desktop:build:win
npm run desktop:build:win:portable
npm run desktop:build:mac
npm run desktop:dist:extension
npm run landing:dev
npm run landing:build
npm run test
```

Track B will add:

```bash
npm run web:dev
npm run web:build
npm run web:start
npm run web-extension:build
```

## A4 Path Rewrite Checklist

After moving desktop, update these path-sensitive areas:

```text
apps/desktop/main.js
apps/desktop/electron-builder.yml
apps/desktop/setup.sh
apps/desktop/scripts/*
apps/desktop/backend runtime path assumptions
```

Known current `main.js` assumptions that should still work from `apps/desktop`:

```text
__dirname/backend
__dirname/renderer/index.html
__dirname/chrome_extension
__dirname/setup.sh
__dirname/scripts/win-alt-ptt.ps1
```

If Electron is launched with cwd at `apps/desktop`, many dev-mode paths can remain unchanged.

Root scripts should invoke desktop using:

```bash
npm --workspace apps/desktop start
```

That means Electron's app root should be `apps/desktop`, preserving most current relative path behavior.

## Track A Completion Definition

Track A is complete when:

```text
apps/desktop contains the current desktop app
apps/landing contains the current landing app
root package.json is a workspace orchestrator
root commands work for desktop and landing
desktop starts from root
desktop packaging config no longer points to missing files
docs are normalized under docs/
known backend syntax blocker is fixed
Python test environment is rebuildable
baseline tests can run from the new layout
```

## A1 Completion Criteria

A1 is complete when:

```text
target monorepo layout is documented
npm workspaces are chosen
app/package boundaries are documented
A2 move map is documented
root command contract is documented
path rewrite checklist is documented
```

Status: complete.
