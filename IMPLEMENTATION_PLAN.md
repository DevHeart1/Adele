# Adele Monorepo And Web Product Implementation Plan

Absolutely. No implementation yet. Here’s the detailed milestone plan I’d use to turn Adele into a clean monorepo and then build Adele Web as a full web-native version.

## North Star

Adele becomes a multi-surface agent platform:

```text
Adele Desktop = local OS + browser automation
Adele Web     = cloud/browser/MCP automation
Shared Core   = schemas, protocols, memory/task models, browser actions
```

Track A should be completed first because it cleans the foundation. Track B then builds Adele Web on top of the new structure.

---

## Track A: Monorepo Migration

### A0. Baseline Audit And Freeze

Goal: capture the current state before moving anything.

Steps:

1. Record current root structure.
2. Record current `npm` scripts.
3. Record Electron build assumptions.
4. Record Python backend entrypoint.
5. Record Chrome extension paths.
6. Record known broken issues separately:
   - `backend/agent/memory.py` syntax error.
   - missing `build/adele-nsis-macros.nsh`.
   - docs path mismatch.
   - vulnerable npm packages.

Tests:

```bash
git status --short
npm run --silent
node -e "JSON.parse(require('fs').readFileSync('package.json','utf8')); console.log('root package ok')"
python -m py_compile backend/servers/local_server.py
```

Expected:

- Clean inventory.
- Known failures documented, not mixed with migration errors.

---

### A1. Define Target Monorepo Layout

Goal: create the final structure contract.

Target:

```text
Adele/
  apps/
    desktop/
      main.js
      preload.js
      package.json
      electron-builder.yml
      renderer/
      backend/
      chrome_extension/
      build/
      scripts/
      tests/
      benchmarks/
      experiments/
      setup.sh

    web/
      # created in Track B

    web-extension/
      # created in Track B

  packages/
    shared/
    agent-core/
    browser-automation/
    connectors/

  infra/
    aws/

  docs/
    architecture/
    submission/
    desktop/
    web/

  package.json
  package-lock.json or workspace lockfile
  README.md
  .gitignore
```

Steps:

1. Decide workspace package manager.
2. I recommend **npm workspaces** for minimum disruption.
3. Define root scripts:
   - `desktop:start`
   - `desktop:build:win`
   - `desktop:build:mac`
   - `web:dev`
   - `web:build`
   - `extension:build`
   - `test`
4. Root `package.json` becomes workspace orchestrator.
5. Desktop gets its own app-level `package.json`.

Tests:

- None yet, this is design only.

Expected:

- Clear migration contract before file movement.

---

### A2. Move Desktop Files Into `apps/desktop`

Goal: relocate current desktop app without changing behavior.

Move these into `apps/desktop`:

```text
main.js
preload.js
renderer/
backend/
chrome_extension/
build/
scripts/
tests/
benchmarks/
experiments/
setup.sh
electron-builder.yml
icon.png
CONTRIBUTING.md
```

Keep at root:

```text
.git/
.gitignore
LICENSE
README.md
package.json initially or converted root package
package-lock.json initially or regenerated
adele-docs/ temporarily, then normalize to docs/
```

Steps:

1. Create `apps/desktop`.
2. Move desktop-specific files.
3. Preserve relative structure inside `apps/desktop`.
4. Do not refactor internals yet.
5. Do not rename CIARA files yet unless needed for build correctness.

Tests:

```bash
git status --short
Test-Path apps/desktop/main.js
Test-Path apps/desktop/backend/servers/local_server.py
Test-Path apps/desktop/renderer/index.html
Test-Path apps/desktop/chrome_extension/manifest.json
```

Expected:

- Desktop app physically lives under `apps/desktop`.
- No behavior changes yet.

---

### A3. Convert Root To Workspace

Goal: root becomes monorepo controller.

Root `package.json` should become something like:

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
    "desktop:build:mac": "npm --workspace apps/desktop run build:mac",
    "test": "npm --workspaces run test --if-present"
  }
}
```

Steps:

1. Move current root `package.json` to `apps/desktop/package.json`.
2. Create new root `package.json`.
3. Decide lockfile strategy:
   - simplest: one root `package-lock.json` for all workspaces.
4. Run `npm install` from root to generate workspace lockfile.
5. Verify desktop package name remains `adele`.

Tests:

```bash
npm install
npm --workspace apps/desktop run --silent
npm run desktop:start
```

Expected:

- npm workspace resolves desktop dependencies.
- Desktop app can still start through root script.

---

### A4. Fix Desktop Path Assumptions

Goal: update paths broken by relocation.

Likely affected areas:

- `main.js`
- `electron-builder.yml`
- packaging scripts
- Python backend cwd
- extension export paths
- build resource paths
- setup scripts
- docs links

Important path checks in `main.js`:

```text
APP_ROOT
BACKEND_ROOT
getVenvRoot()
getAppIconPath()
CHROME_EXT_SOURCE
spawn cwd
setup.sh location
scripts/win-alt-ptt.ps1
```

Steps:

1. Update paths to assume app root is `apps/desktop`.
2. Ensure packaged mode still uses `process.resourcesPath`.
3. Ensure dev mode uses `__dirname` inside `apps/desktop`.
4. Ensure Python backend starts from `apps/desktop`.
5. Ensure `ADELE_DATA_DIR` still points to userData, not repo.
6. Ensure extension export copies `apps/desktop/chrome_extension`.

Tests:

```bash
npm run desktop:start
```

Manual test:

- App opens.
- Onboarding/settings open.
- Backend start does not path-fail.
- Extension export path works.

Expected:

- Desktop dev mode works from monorepo root.

---

### A5. Fix Windows Builder Resource Paths

Goal: make packaging config valid after relocation.

Known issue:

```text
electron-builder.yml references build/adele-nsis-macros.nsh
actual file is build/ciara-nsis-macros.nsh
```

Decision:

- Rename `ciara-nsis-macros.nsh` to `adele-nsis-macros.nsh`.
- Rename `ciara-nsis-installSection.nsh` similarly if referenced.
- Update internal strings from CIARA to ADELE.

Steps:

1. Update `apps/desktop/electron-builder.yml`.
2. Ensure `files` paths work relative to `apps/desktop`.
3. Ensure `extraResources` includes:
   - `backend`
   - `setup.sh`
   - `scripts/win-alt-ptt.ps1`
   - `build/icon.ico`
   - `chrome_extension`
   - bundled Python/wheelhouse if present.
4. Confirm output directory:
   - either root `release/`
   - or `apps/desktop/release/`
5. I recommend `apps/desktop/release`.

Tests:

```bash
npm run desktop:build:win
```

Expected:

- Installer generation starts and no longer fails on missing NSIS include.
- If Python runtime/wheelhouse missing, failure should be about runtime prep, not config.

---

### A6. Normalize Docs

Goal: make docs match new structure.

Steps:

1. Move `adele-docs/` to `docs/`.
2. Update README links from `docs/...` if needed.
3. Split docs:
   - `docs/desktop`
   - `docs/web`
   - `docs/architecture`
   - `docs/submission`
4. Fix mojibake in `CONTRIBUTING.md` or convert it into `docs/desktop/DEVELOPER_GUIDE.md`.
5. Create root README explaining:
   - Adele Desktop
   - Adele Web
   - shared packages
   - workspace commands.

Tests:

```bash
rg -n "adele-docs|docs/screenshots|CIARA|ciara" README.md docs apps/desktop -g "!node_modules"
```

Expected:

- No broken docs references.
- No accidental stale CIARA branding except historical notes.

---

### A7. Fix Desktop Import/Startup Blockers

Goal: fix known issues discovered during audit after structure is stable.

Main blocker:

- `apps/desktop/backend/agent/memory.py` invalid MongoDB import block.

Steps:

1. Fix `try/except ImportError`.
2. Ensure `ObjectId` import is reachable.
3. Keep fast Mongo timeout wrapper.
4. Re-run compile checks.

Tests:

```bash
python -m py_compile apps/desktop/backend/agent/memory.py
python -m py_compile apps/desktop/backend/servers/local_server.py
python -m py_compile apps/desktop/backend/agent/core_v2.py
```

Expected:

- Core backend imports compile.

---

### A8. Rebuild Python/Test Environment

Goal: make desktop tests runnable from new location.

Steps:

1. Decide venv location:
   - `apps/desktop/.venv`, or
   - root `.venv`.
2. I recommend `apps/desktop/.venv` for app isolation.
3. Update setup docs/scripts.
4. Install requirements.
5. Install pytest if not already in requirements/dev requirements.
6. Consider adding `backend/requirements-dev.txt`.

Tests:

```bash
cd apps/desktop
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
.venv\Scripts\python.exe -m pip install pytest
.venv\Scripts\python.exe -m pytest -q tests/test_gemini_provider.py tests/test_agent_schema.py
```

Expected:

- Targeted tests run.
- Any failures are real code issues, not missing environment.

---

### A9. Desktop Regression Test Pass

Goal: verify the moved desktop app still behaves.

Automated tests:

```bash
npm run desktop:start
npm --workspace apps/desktop run dist:extension
cd apps/desktop
.venv\Scripts\python.exe -m pytest -q tests
```

Manual tests:

1. Launch desktop app.
2. Settings loads.
3. Save/load credentials works.
4. Backend starts.
5. Browser bridge server starts.
6. Chrome extension export works.
7. Extension can handshake with local bridge.
8. Text command reaches backend.
9. Memory paths still point to user data.

Expected:

- Desktop functionality preserved after monorepo migration.

---

### A10. Track A Completion Criteria

Track A is done when:

- Current desktop app lives in `apps/desktop`.
- Root is a real npm workspace monorepo.
- Desktop starts from root script.
- Desktop build config paths are valid.
- Docs reflect new structure.
- Known syntax blocker fixed.
- Tests can run in a documented environment.
- No accidental unrelated refactor was introduced.

---

## Track B: Adele Web Full Product

### B0. Define Adele Web Product Contract

Goal: define what “full Adele Web” means.

Adele Web should include:

1. Chat/command interface.
2. Cloud memory vault.
3. Browser automation through web extension.
4. Task planning and action timeline.
5. Connected tools through MCP/Composio.
6. Approval queue.
7. Audit logs.
8. User settings/privacy controls.
9. DynamoDB persistence.
10. Vercel deployment.

Tests:

- Product spec review only.

Expected:

- Clear MVP scope and non-goals.

---

### B1. Scaffold `apps/web`

Goal: create Next.js Vercel app.

Recommended stack:

- Next.js App Router.
- TypeScript.
- Tailwind.
- shadcn/ui optional.
- Zod.
- AWS SDK v3.
- Auth later, simple user ID first for hackathon.

Steps:

1. Create `apps/web`.
2. Add Next.js.
3. Add route groups:
   - dashboard
   - memory
   - tasks
   - connectors
   - browser
   - settings.
4. Add env example.

Tests:

```bash
npm --workspace apps/web run dev
npm --workspace apps/web run build
```

Expected:

- Web app runs locally.
- Web app builds.

---

### B2. Create `packages/shared`

Goal: shared contracts between desktop/web/extensions.

Schemas:

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

Steps:

1. Create TypeScript package.
2. Add Zod schemas.
3. Export inferred TS types.
4. Add JSON-compatible schema design.
5. Keep names compatible with desktop Python models where possible.

Tests:

```bash
npm --workspace packages/shared run build
npm --workspace packages/shared run test
```

Expected:

- Shared schemas compile.
- Web can import from shared.

---

### B3. DynamoDB Infrastructure Plan

Goal: define AWS database structure.

Recommended table:

```text
Table: AdeleWeb
PK: pk
SK: sk

GSI1PK: gsi1pk
GSI1SK: gsi1sk
```

Entity patterns:

```text
USER#{userId} / PROFILE#default
USER#{userId} / MEMORY#{memoryId}
USER#{userId} / TASK#{taskId}
USER#{userId} / TASK#{taskId}#STEP#{stepId}
USER#{userId} / APPROVAL#{approvalId}
USER#{userId} / CONNECTOR#{connectorId}
USER#{userId} / BROWSER_SESSION#{sessionId}
```

Steps:

1. Create infra docs.
2. Add AWS env variables:
   - `AWS_REGION`
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `ADELE_DYNAMODB_TABLE`
3. Add setup instructions.
4. Optional: add table creation script.

Tests:

```bash
aws dynamodb describe-table --table-name AdeleWeb
```

Expected:

- Table exists.
- Screenshot can prove AWS Database usage.

---

### B4. Implement Web Persistence Layer

Goal: DynamoDB CRUD helpers.

Modules:

```text
apps/web/src/server/db/client.ts
apps/web/src/server/db/memory.ts
apps/web/src/server/db/tasks.ts
apps/web/src/server/db/approvals.ts
apps/web/src/server/db/connectors.ts
```

Steps:

1. Build DynamoDB client.
2. Add marshalling helpers.
3. Add CRUD for memories.
4. Add CRUD for tasks.
5. Add CRUD for approvals.
6. Add health check.

Tests:

```bash
npm --workspace apps/web run test
curl http://localhost:3000/api/health/aws
```

Expected:

- API can read/write test item to DynamoDB.
- Health route confirms configured DB.

---

### B5. Cloud Memory Vault UI

Goal: build the memory board you described.

Pages:

```text
/memory
/memory/[id]
/memory/new
```

Features:

1. View all memories.
2. Search/filter by tag/type/status.
3. Create memory.
4. Edit memory.
5. Delete memory.
6. Reset memory vault.
7. Approve/reject pending memory.
8. Show source:
   - web
   - browser extension
   - connector
   - desktop import.

Tests:

```bash
npm --workspace apps/web run build
```

Manual tests:

- Create memory.
- Edit memory.
- Delete memory.
- Reset test memories.
- Confirm DynamoDB updates.

Expected:

- Fully usable cloud memory vault.

---

### B6. Task Runs And Audit Timeline

Goal: every Adele Web action is visible.

Pages:

```text
/tasks
/tasks/[id]
/approvals
```

Features:

1. Task list.
2. Task status:
   - queued
   - planning
   - waiting_for_approval
   - running
   - completed
   - failed.
3. Step timeline.
4. Browser actions log.
5. Tool calls log.
6. Approval records.

Tests:

- Create fake task via API.
- Render task timeline.
- Add action log.
- Approve/reject approval.

Expected:

- User can see what Adele did and why.

---

### B7. Scaffold `apps/web-extension`

Goal: create Adele Web Chrome extension.

Structure:

```text
apps/web-extension/
  manifest.json
  src/
    background.ts
    content-script.ts
    popup.tsx
    options.tsx
  public/
```

Permissions:

- activeTab
- scripting
- storage
- tabs
- optionally sidePanel later.

Steps:

1. Create MV3 extension.
2. Add build system.
3. Add popup showing connection state.
4. Add options for Adele Web URL.
5. Add pairing token storage.

Tests:

```bash
npm --workspace apps/web-extension run build
```

Manual:

- Load unpacked extension.
- Popup opens.
- Options save server URL.

Expected:

- Extension installable.

---

### B8. Extension Pairing And Session Model

Goal: securely connect browser extension to Adele Web.

Flow:

1. User opens Adele Web.
2. User clicks “Pair Extension.”
3. Web shows short pairing code.
4. Extension enters/receives pairing code.
5. Web creates browser session token.
6. Extension stores short-lived token.
7. Extension reports active tab/session state.

API:

```text
POST /api/extension/pair/start
POST /api/extension/pair/complete
POST /api/browser/session/heartbeat
```

Tests:

- Start pairing.
- Complete pairing.
- Heartbeat appears in web UI.
- Expired token is rejected.

Expected:

- Web app knows extension is connected.

---

### B9. Browser Snapshot Protocol

Goal: extension can read active page like desktop bridge.

Shared schema:

```text
BrowserSnapshot
BrowserElementRef
```

Extension captures:

1. URL.
2. Title.
3. Visible text.
4. Forms.
5. Buttons.
6. Inputs.
7. Links.
8. ARIA labels.
9. Element bounding boxes.
10. Stable refs.

API:

```text
POST /api/browser/snapshot
GET /api/browser/snapshot/latest
```

Tests:

- Open test page.
- Capture snapshot.
- Confirm web UI displays active page data.
- Confirm refs are stable enough for click/type.

Expected:

- Adele Web can “see” active browser tab.

---

### B10. Browser Action Execution

Goal: Adele Web can act in browser through extension.

Actions:

```text
click_ref
type_ref
select_ref
scroll
read_page
extract_form
highlight_ref
```

Flow:

```text
Web agent queues action
Extension polls or receives action
Extension executes action
Extension returns result
Web logs result
```

API:

```text
POST /api/browser/actions
GET /api/browser/actions/pending
POST /api/browser/actions/result
```

Tests:

- Test page with input/button.
- Queue `type_ref`.
- Queue `click_ref`.
- Verify DOM changed.
- Verify action result stored in DynamoDB.

Expected:

- Web automation loop works.

---

### B11. Adele Web Agent Runtime MVP

Goal: command input can plan and execute simple browser/memory tasks.

Initial runtime can be simple:

```text
User command
 -> classify intent
 -> get current browser snapshot
 -> choose memory/tool/browser action
 -> execute
 -> log steps
 -> respond
```

Tasks to support first:

1. “Summarize this page.”
2. “Save this page to memory.”
3. “Fill this form from my profile.”
4. “Click the sign in button.”
5. “Find jobs on this page and save them.”
6. “Draft an application answer from my profile.”

Tests:

- Unit test planner classification.
- Integration test save-page-to-memory.
- Integration test fill-form-on-test-page.

Expected:

- Adele Web feels like an agent, not a dashboard.

---

### B12. Approval And Safety Layer

Goal: prevent dangerous automation.

Require approval for:

- submit form;
- send email;
- apply job;
- purchase/checkout;
- delete data;
- post publicly;
- connect/disconnect tools;
- access sensitive domains if configured.

Features:

1. Approval queue.
2. Approve/reject buttons.
3. “Always allow for this site/action” optional later.
4. Audit record for approval decision.

Tests:

- Agent tries submit.
- Approval request created.
- Action blocked until approved.
- Rejection cancels action.

Expected:

- Safe human-in-the-loop control.

---

### B13. MCP/Composio Connector Layer

Goal: user can connect external tools.

Abstraction:

```text
ConnectorProvider
ToolDefinition
ToolCall
ToolResult
```

Providers:

1. Composio first.
2. HTTP MCP later.
3. Local bridge MCP later.

Pages:

```text
/connectors
/mcp
```

First connectors:

- Gmail search/read.
- Google Calendar create/list.
- Notion or Google Drive optional.

Steps:

1. Add connector registry.
2. Add connected account model.
3. Add tool list UI.
4. Add tool call logging.
5. Add one working connector.

Tests:

- Connect test provider.
- List tools.
- Run safe read-only tool.
- Store result in task log.

Expected:

- Adele Web can use cloud tools outside browser DOM.

---

### B14. Job Application Demo Workflow

Goal: build flagship hackathon demo.

Workflow:

1. User opens a job listing.
2. Adele Web extension reads page.
3. Adele extracts title/company/location/requirements.
4. Adele compares against user memory/profile.
5. Saves listing to DynamoDB.
6. Opens or detects application form.
7. Fills safe fields.
8. Drafts cover letter answer.
9. Stops before submit.
10. User approves or edits.

Tests:

- Use controlled test job page.
- Use real job page if stable.
- Confirm memory saved.
- Confirm form fill works.
- Confirm submit approval triggers.

Expected:

- Strong demo showing full Adele Web.

---

### B15. Desktop/Web Sync Plan

Goal: bridge Adele Desktop and Adele Web later.

Do not overbuild for hackathon, but define path.

Options:

1. Desktop exports local vault JSON.
2. Web imports JSON.
3. Desktop sync script pushes to Adele Web API.
4. Future authenticated sync.

Minimum:

- Import/export memory JSON compatible with `packages/shared`.

Tests:

- Export sample memory.
- Import to web.
- View in cloud vault.

Expected:

- Desktop and web story feels connected.

---

### B16. Vercel Deployment

Goal: deploy Adele Web.

Steps:

1. Add Vercel project.
2. Configure env vars.
3. Deploy.
4. Verify DynamoDB connection from deployed API.
5. Add published URL.
6. Record Vercel Team ID.

Tests:

```bash
npm --workspace apps/web run build
```

Deployment tests:

- Visit deployed app.
- Create memory.
- Capture AWS proof screenshot.
- Confirm API writes to DynamoDB.

Expected:

- Production web app link ready for Devpost.

---

### B17. Hackathon Submission Package

Goal: complete H0 requirements.

Required:

1. Text description.
2. State AWS database used: DynamoDB.
3. Less than 3-minute demo video.
4. Published Vercel Project Link.
5. Vercel Team ID.
6. Architecture diagram.
7. Screenshot proving AWS Database usage.

Architecture diagram should show:

```text
User
 -> Adele Web on Vercel
 -> Next.js API routes / Agent runtime
 -> DynamoDB
 -> Chrome Extension
 -> Active Browser Tab
 -> Composio/MCP Connectors
 -> Gmail/Calendar/Other tools
```

Tests:

- Watch full demo video under 3 minutes.
- Click all submission links.
- Confirm deployed app works.

Expected:

- Devpost-ready package.

---

### B18. Track B Completion Criteria

Track B is complete when:

- Adele Web is deployed on Vercel.
- DynamoDB is used for real product data.
- Cloud memory vault works.
- Browser extension pairs with web app.
- Extension can snapshot and automate active tab.
- Agent runtime can complete at least one meaningful web workflow.
- MCP/connector system has at least one working integration or a clean provider abstraction.
- Approval/audit trail exists.
- Hackathon assets are ready.

---

## Suggested Build Order

I would do this exact order:

1. A0-A3: Move into monorepo.
2. A4-A7: Fix paths and blockers.
3. A8-A10: Verify desktop survived.
4. B1-B4: Web app + shared schemas + DynamoDB.
5. B5-B6: Memory vault + task logs.
6. B7-B10: Web extension + browser automation.
7. B11-B12: Agent runtime + safety approvals.
8. B13-B14: Connectors + flagship demo.
9. B16-B17: Deploy + submit.

## Most Important Principle

Track A should be a clean relocation. Track B should be a web-native Adele. Don’t let Track A become a giant refactor, and don’t let Track B become a tiny dashboard. That balance gives you the clean repo and the big product vision.
