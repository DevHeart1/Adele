# ADELE

**ADELE is a local-first AI companion for getting work done across your desktop and browser.** Describe a goal in natural language; ADELE builds a milestone-based plan, asks for approval when needed, carries out the permitted actions, and checks the result.

The repository is a JavaScript/TypeScript and Python monorepo with three product surfaces:

| Surface | Status | Purpose |
| --- | --- | --- |
| **ADELE Desktop** | Active | Electron overlay for voice and text, a local Python agent runtime, desktop automation, and a Chrome browser bridge. |
| **ADELE Web** | B1 scaffold | Next.js dashboard and DynamoDB persistence foundation for browser- and cloud-native workflows. |
| **ADELE Landing** | Active | React/Vite marketing site. |

<p align="center">
  <img src="docs/screenshots/Moonwalk.png" alt="ADELE desktop interface" width="640" />
</p>

## What ADELE does

ADELE is built around the **Sense → Plan → Act → Verify** loop:

1. It gathers relevant local, screen, and browser context.
2. It turns a request into observable milestones with success signals.
3. It uses the appropriate desktop, browser, file, or supported service tool.
4. It verifies the action from tool results, browser state, or visual evidence before reporting completion.

The Desktop app currently supports:

- A compact Electron overlay with text input, voice interaction, global hotkeys, tray controls, and onboarding.
- Local browser automation through the Manifest V3 **ADELE Browser Bridge** Chrome extension: page reading, element discovery, clicks, typing, selection, scrolling, and structured extraction.
- Desktop interaction through native UI, keyboard, mouse, screen, application, file, and system tools. Platform support depends on the installed automation dependencies and operating-system permissions.
- Local session, plan, milestone, screenshot, and vault-memory storage; MongoDB can be configured as an optional backing store.
- Approval and verification hooks for consequential actions. ADELE’s local runtime remains the authority for validating, executing, and verifying actions.
- ChatGPT sign-in through a local Codex App Server process, using **GPT-5.6** exclusively for the supported Desktop LLM path.

The Web app is deliberately separate from Desktop: it is the foundation for browser/cloud workflows, a cloud memory vault, task and approval views, connector management, and DynamoDB-backed records. It does not give the Web app control over the user’s native desktop.

## Built with Codex and GPT-5.6

Codex and GPT-5.6 have two intentionally distinct roles in ADELE: **they accelerated the creation of the product**, and **GPT-5.6 is the Desktop app’s production reasoning component**. In both cases, the team keeps product decisions, source control, and action authority with people and ADELE’s local safety systems.

### From idea to a shippable product

Codex was used as a development collaborator to move from a broad idea—an assistant that can complete work across desktop and browser surfaces—to an implementation that can be reviewed, tested, and packaged. The workflow was deliberately plan-first:

| Stage | How Codex and GPT-5.6 contributed | Durable outcome in this repository |
| --- | --- | --- |
| **Ideation and product definition** | Helped turn user journeys, product boundaries, and safety constraints into concrete requirements rather than a single open-ended agent prompt. | The [implementation plan](IMPLEMENTATION_PLAN.md), [Web product contract](B0_ADELE_WEB_PRODUCT_CONTRACT.md), and desktop/browser/cloud boundaries. |
| **Architecture and delivery planning** | Helped decompose the work into the Electron shell, Python runtime, browser bridge, shared contracts, Web scaffold, packaging, and testable milestones. | The monorepo layout, workspace commands, architecture notes, and shared Zod contracts. |
| **Implementation and refinement** | Assisted with code exploration, implementation, debugging, documentation, and targeted test work across JavaScript/TypeScript and Python. Repository-level `AGENTS.md` guidance constrains those tasks with paths, commands, privacy requirements, and definition-of-done checks. | The Desktop app, Chrome bridge, Web scaffold, test suite, packaging scripts, and this documentation. |
| **Validation and release readiness** | Helped focus review on failure modes: authentication, model selection, streaming, cancellation, redaction, and the boundary between reasoning and real-world actions. | A deterministic fake App Server, provider tests, generated protocol schemas, safe execution traces, and explicit packaging steps. |

This was not “prompt once and ship.” Codex was used in a feedback loop: establish the goal and constraints, inspect the relevant code and docs, make a bounded change, run focused verification, review the diff, and iterate. The [Desktop guidance](apps/desktop/AGENTS.md) makes that workflow reproducible for future contributors.

### GPT-5.6 in the running Desktop app

ADELE Desktop uses **ChatGPT sign-in through Codex App Server** as its only supported production LLM route. At launch, the local backend starts one `codex app-server` child process over stdio—not a public HTTP service—and performs account and model discovery. It accepts `gpt-5.6` and, only when necessary, the GPT-5.6 Sol variant; if neither is available, ADELE shows a connection error instead of silently falling back to another provider or model.

For every user request, GPT-5.6 receives a compact task prompt containing the allowed context, plus a screenshot only when the signed-in model supports image input and ADELE has decided that it is appropriate. It reasons about the task, helps form a concise plan, and returns either a user-facing response or a constrained, schema-shaped selection from Adele’s permitted tools. Text streams back to the overlay as it arrives, while the local runtime records only safe trace metadata such as model, reasoning effort, token counts, duration, and outcome.

```text
User request and local context
        │
        ▼
ADELE agent: plan + permitted tool schema
        │
        ▼
Codex App Server over local stdio ──► GPT-5.6 reasoning and structured response
        │
        ▼
ADELE validates the response ──► approval gate ──► local tool execution ──► verification
```

GPT-5.6 is therefore the **reasoning layer**, not the automation authority. It cannot directly click, type, send, purchase, delete, read credentials, or bypass a user approval. Adele validates every proposed tool call, applies its local action policy, runs the action through its own registry, and verifies the observable result. Dynamic App Server tools are disabled until they can be routed through those same controls.

### Production guardrails

- **Authentication stays in Codex.** Adele launches a validated HTTPS sign-in URL and receives only sanitized connection state; it does not read `auth.json`, browser cookies, passwords, or ChatGPT tokens.
- **The model is constrained.** The App Server thread is created with a read-only sandbox, no direct approvals, and developer instructions that limit it to safe plans and tool selections.
- **Execution is local and observable.** The Python runtime owns the tool registry, approvals, retries, browser/desktop state checks, and visual verification for UI-changing work.
- **Failures are handled deliberately.** A cancelled, timed-out, or failed model turn is interrupted or reset locally rather than being treated as a successful action.
- **Sensitive data is minimized.** Raw prompts, responses, screenshots, screenshot paths, private tool arguments, and hidden reasoning are excluded from normal diagnostics. Temporary screenshots used for a turn are removed when that turn ends.

For the implementation-level protocol, model-selection behavior, and the exact test command, see [Codex App Server integration](docs/CODEX_APP_SERVER_INTEGRATION.md) and [Build Week Desktop setup](docs/BUILD_WEEK_DESKTOP_SETUP.md).

## Architecture

```text
                         ChatGPT sign-in
                                │
                    codex app-server (local stdio)
                                │
┌──────────────────────────── ADELE Desktop ────────────────────────────┐
│  Electron shell and overlay                                             │
│       │ IPC                                                             │
│       ▼                                                                 │
│  Local Python runtime ───────► planner / agent / tool registry         │
│       │                                  │                              │
│       │ WebSocket :8000                  ├─ local UI, files, apps       │
│       ├──────────────────────────────────└─ memory and verification     │
│       │                                                                  │
│       └── WebSocket :8765 ──► ADELE Browser Bridge ──► active tabs      │
└───────────────────────────────────────────────────────────────────────┘

ADELE Web (Next.js) ──► DynamoDB / planned browser extension and connected services
```

The Desktop backend binds its WebSocket services to `127.0.0.1` by default. The model provider is a reasoning service only: it never receives direct authority to run unvalidated desktop actions.

## Repository layout

```text
apps/
  desktop/                   Electron app and local Python runtime
    renderer/                Overlay user interface
    backend/                 Agent, provider, tool, memory, and server code
    chrome_extension/        Manifest V3 desktop browser bridge
    build/                   App icons and installer resources
    scripts/                 Packaging and runtime-preparation utilities
    tests/                   Desktop test suite and fake Codex App Server
  web/                       Next.js B1 dashboard and DynamoDB persistence layer
  landing/                   React/Vite marketing site
packages/
  shared/                    Zod schemas and TypeScript contracts
docs/                        Product, desktop, architecture, security, and demo docs
```

## Requirements

For Desktop development, install:

- A current Node.js LTS release with npm.
- Python **3.10–3.13**. ADELE creates a virtual environment for the local backend; packaged Windows builds bundle their own supported Python runtime.
- [Codex](https://openai.com/codex/) Desktop or CLI, signed in with a ChatGPT account that can use GPT-5.6.
- Google Chrome or another Chromium browser to use the desktop browser bridge.

Voice input, screen access, and desktop automation may require operating-system permissions. Optional MongoDB and ElevenLabs configuration is not required to start the core Desktop app.

## Quick start: ADELE Desktop

From the repository root:

```powershell
npm install
npm run desktop:start
```

On the first launch, the Electron app prepares the Python environment and starts the backend automatically. In onboarding, select **Continue with ChatGPT**. Authentication happens in Codex; ADELE never asks for, reads, or stores a ChatGPT password, cookie, access token, refresh token, or `auth.json` file.

Once the connection panel reports **Connected with ChatGPT**, confirm that the model is **GPT-5.6**. If GPT-5.6 is not available to the account, ADELE reports the connection problem rather than silently switching to a different model.

If PowerShell policy blocks `npm.ps1`, run the same commands with `npm.cmd` instead.

### Prepare a Python environment for tests

The app bootstraps its own runtime, but backend development and tests use an explicit virtual environment:

```powershell
cd apps\desktop
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
```

Run the primary provider integration test (it uses a local fake App Server, so it does not need network access or a personal ChatGPT account):

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_codex_app_server.py -q
```

## Configure the desktop browser bridge

The Chrome extension is sourced from `apps/desktop/chrome_extension`. With ADELE running:

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Select **Load unpacked** and choose `apps/desktop/chrome_extension`.
4. Optionally pin **ADELE Browser Bridge** to the toolbar.
5. Open the extension’s options only if you need to change the local bridge URL or token. Its default URL is `ws://127.0.0.1:8765`.

To create a distributable archive with its installation guide:

```powershell
npm run desktop:dist:extension
```

The archive is written to `apps/desktop/dist/adele-browser-bridge.zip`.

## Run the other apps

### Landing site

```powershell
npm run landing:dev
npm run landing:build
```

### ADELE Web scaffold

```powershell
npm run web:dev
npm run web:build
```

Copy `apps/web/.env.example` to `apps/web/.env.local` before using AWS-backed features. The Web scaffold can create its DynamoDB table with:

```powershell
npm --workspace apps/web run db:create-table
```

This command creates cloud infrastructure in the configured AWS account, so review the environment variables and account before running it.

## Commands

| Command | Description |
| --- | --- |
| `npm run desktop:start` | Start the Electron Desktop app and local backend. |
| `npm run desktop:dist:extension` | Package the Chrome browser bridge ZIP. |
| `npm run desktop:build:win` | Prepare the Windows Python runtime and wheelhouse, then build the NSIS installer. |
| `npm run desktop:build:win:portable` | Build a portable Windows artifact. |
| `npm run desktop:build:mac` | Build the macOS desktop artifact. |
| `npm run landing:dev` | Run the Vite landing site. |
| `npm run landing:build` | Create a production landing-site build. |
| `npm run web:dev` | Run the Next.js Web scaffold. |
| `npm run web:build` | Build the Web scaffold. |
| `npm test` | Run each workspace’s available test command. |
| `npm --workspace packages/shared run test` | Build and test the shared TypeScript contracts. |
| `npm --workspace apps/web run test` | Test the Web persistence layer. |

## Configuration

The Desktop app has safe defaults. Most developers do not need to set environment variables.

| Variable | Use |
| --- | --- |
| `ADELE_CODEX_EXECUTABLE` | Developer override for the local Codex executable. |
| `ADELE_DATA_DIR` | Overrides the local storage root. Outside Electron and tests, it defaults to `~/.adele`. |
| `ADELE_BACKEND_HOST`, `ADELE_BACKEND_PORT`, `ADELE_BACKEND_WS_URL` | Override the local backend connection, which defaults to `127.0.0.1:8000`. |
| `ADELE_BROWSER_BRIDGE_HOST`, `ADELE_BROWSER_BRIDGE_PORT`, `ADELE_BROWSER_BRIDGE_TOKEN` | Configure the local browser-extension bridge, which defaults to port `8765`. |
| `LIQUID_HOTKEY` | Comma- or semicolon-separated override for the command hotkey. Defaults include `CommandOrControl+Shift+Space` and `Alt+Space`. |
| `ADELE_SETTINGS_HOTKEY` | Override for the settings hotkey; default is `CommandOrControl+,`. |
| `ADELE_MONGODB_URI`, `ADELE_MONGODB_DB` | Optional MongoDB backing store for memory and runtime records. |
| `ELEVENLABS_API_KEY` and related `ELEVENLABS_*` settings | Optional ElevenLabs speech-to-text and text-to-speech integration. |

Do not configure a main-model API key or switch the production Desktop provider: the active path is Codex App Server with ChatGPT sign-in and GPT-5.6. Legacy provider code remains for experiments and compatibility only; it is not the supported Desktop composition.

### Local data and privacy

The Python runtime creates these directories beneath `ADELE_DATA_DIR` (or `~/.adele` for direct CLI/test execution):

```text
sessions/  vault/  screenshots/  plans/  milestones/  memories/  conversations/
```

The packaged Desktop application sets this root inside its application data directory. Do not commit these files, `.env` files, bundled runtimes, wheelhouses, or generated Codex schemas.

## Development notes

### Desktop runtime boundaries

- **Electron** owns the desktop window, tray, hotkeys, onboarding, and IPC surface.
- **Python backend** owns the local WebSocket servers, agent loop, memory, tool registry, approvals, and verification.
- **Browser Bridge** runs inside the browser and handles active-tab context and requested browser actions through the local bridge.
- **Codex App Server** is a child process on stdio. It does not expose a public port and does not execute ADELE’s tools directly.

When changing the Codex App Server protocol, regenerate the schemas rather than editing generated files:

```powershell
codex app-server generate-json-schema --out apps/desktop/backend/providers/codex_schemas
```

Update the protocol documentation and fake-server tests with the change. Generated schemas are intentionally ignored by Git.

### Shared contracts

`@adele/shared` defines JSON-compatible Zod schemas for tasks, plans, milestones, approvals, browser actions, memory, connectors, and audit events. Keep runtime-specific objects—DOM nodes, functions, binary buffers, and class instances—out of this package.

### Build and packaging

The Windows installer build runs `prepare:python:win` and `prepare:wheelhouse:win` before Electron Builder. This produces a bundled Python runtime and offline wheelhouse used by a first run of the packaged app. macOS builds use Electron Builder’s macOS targets. Builds produce local artifacts and may need platform-specific signing or permission setup before distribution.

## Safety model

ADELE is designed so model output is not an execution authority:

- The local runtime validates tool calls and retains its approval and verification gates.
- UI-changing actions can be checked using tool results, browser/DOM state, and visual evidence.
- Sensitive credentials and raw ChatGPT authentication material stay outside ADELE’s data and diagnostics.
- Normal diagnostics are limited to safe operational metadata; they exclude raw prompts, responses, screenshots, hidden reasoning, and sensitive tool arguments.
- Temporary screenshots sent for a turn are removed when that turn completes, errors, times out, or is cancelled.

Read the full [security and privacy notes](docs/ADELE_SECURITY_AND_PRIVACY.md) before changing authentication, logging, action execution, or data retention.

## Documentation

- [Documentation index](docs/README.md)
- [Desktop guide](docs/desktop/GUIDE.md)
- [Build Week Desktop setup](docs/BUILD_WEEK_DESKTOP_SETUP.md)
- [Codex App Server integration](docs/CODEX_APP_SERVER_INTEGRATION.md)
- [Security and privacy](docs/ADELE_SECURITY_AND_PRIVACY.md)
- [Architecture notes](docs/architecture/README.md)
- [Web product plan](docs/web/README.md)
- [Shared contracts](packages/shared/README.md)
- [Hackathon submission plan](docs/submission/HACKATHON_SUBMISSION.md)

## Contributing

Keep changes scoped to the relevant product surface. In particular, Desktop code belongs under `apps/desktop`; do not mix Web or landing-site changes into Desktop work. Preserve the Desktop security boundary: Adele never reads browser cookies, passwords, API keys, ChatGPT tokens, or Codex `auth.json`, and the App Server must never bypass Adele’s tool-validation, approval, or verification layers.

Before opening a change that affects the provider integration, run:

```powershell
cd apps\desktop
.\.venv\Scripts\python.exe -m pytest tests\test_codex_app_server.py -q
```

## License

[MIT](LICENSE)
