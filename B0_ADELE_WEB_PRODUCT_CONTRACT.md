# B0 Adele Web Product Contract

Date: 2026-06-18

## Goal

Define what "full Adele Web" means before implementation begins. This contract is the Track B source of truth for scope, non-goals, user experience, system boundaries, and acceptance criteria.

## Product Definition

Adele Web is the browser/cloud version of Adele. It gives users an Adele agent that can understand tasks, remember user-approved context, automate browser workflows through a Chrome extension, and use connected cloud tools through MCP/Composio-style connectors.

Adele Web is not a thin memory dashboard. It is a full web-native Adele product with its own chat interface, task runtime, cloud memory vault, browser extension, connector system, approval queue, audit log, and deployment path.

## Product Variants

### Adele Desktop

Adele Desktop remains the local computer assistant. It controls local apps, local files, native windows, desktop browser sessions, voice/hotkey flows, and local runtime state.

### Adele Web

Adele Web is the cloud/browser assistant. It controls web apps through the Adele Web Chrome extension, uses cloud memory and task state, connects to external tools through user-configured connectors, and runs from a Vercel-hosted web app.

The two products should feel like Adele, but they are separate runtime surfaces. Desktop should not be forced into the web app, and the web app should not depend on a desktop process to work.

## MVP Scope

The B0 MVP for Adele Web includes these ten product capabilities:

1. Chat and command interface.
2. Cloud memory vault.
3. Browser automation through a web Chrome extension.
4. Task planning and action timeline.
5. Connected tools through MCP/Composio-style connectors.
6. Approval queue for sensitive actions.
7. Audit logs for agent decisions and tool calls.
8. User settings and privacy controls.
9. DynamoDB persistence.
10. Vercel deployment.

## Primary Demo Workflow

The first complete Adele Web demo should be a job-application workflow:

1. User opens a job listing in the browser.
2. User asks Adele Web to evaluate or apply for the role.
3. Adele Web reads the active tab through the extension.
4. Adele Web compares the job to saved profile memory.
5. Adele Web saves the listing and extracted requirements to DynamoDB.
6. Adele Web drafts answers or fills safe application fields.
7. Adele Web pauses before final submission.
8. User reviews the approval queue.
9. User approves, edits, or rejects the final action.
10. Adele Web writes an audit trail of what happened.

## Core User Stories

### Chat

As a user, I can type a natural-language task into Adele Web and see Adele respond with a plan, progress updates, tool activity, and a final result.

Acceptance:

- User can start a task from the main web interface.
- Adele can show whether it is planning, acting, waiting for approval, blocked, or done.
- Adele can return structured cards for memory, tasks, approvals, and browser actions.

### Cloud Memory Vault

As a user, I can view, edit, delete, and reset saved memory that Adele Web uses.

Acceptance:

- Memory entries have categories, titles, content, timestamps, source metadata, and review status.
- User can manually create, edit, delete, and approve memory.
- Adele can save task-relevant memory with user-visible provenance.
- Memory can be searched and filtered.

### Browser Automation

As a user, I can ask Adele Web to act on websites I have open, using a web Chrome extension.

Acceptance:

- Extension can connect to the web app/runtime.
- Extension can publish an active-tab snapshot.
- Extension can receive approved browser actions.
- Browser actions include read page, find element, click, type, select, scroll, and extract data.
- Adele pauses for approval before irreversible or sensitive actions.

### Task Planning And Timeline

As a user, I can see what Adele plans to do and what it already did.

Acceptance:

- Task runs have a goal, status, created time, updated time, steps, and final result.
- Steps show tool name, arguments summary, status, output summary, and errors.
- Long tasks can pause for approval or clarification.

### Connectors

As a user, I can connect external services that Adele Web can use.

Acceptance:

- Connector screen lists available connector types.
- User can add, disable, or remove a connector.
- Connector configs are scoped to a user.
- Tool execution records which connector was used.
- MCP/Composio integration is treated as the connector abstraction, even if the hackathon MVP uses a small local adapter first.

### Approval Queue

As a user, I can review sensitive actions before Adele performs them.

Acceptance:

- Approval requests show action type, target, risk level, reason, and proposed payload.
- User can approve, reject, or edit where supported.
- Submit, purchase, send message/email, delete, payment, credential, and external write operations require approval.

### Audit Logs

As a user, I can inspect what Adele did and why.

Acceptance:

- Audit logs include task id, step id, actor, event type, timestamp, tool name, input summary, output summary, and approval status.
- Sensitive values are redacted.
- Logs are queryable by task and user.

### Settings And Privacy

As a user, I can control what Adele Web remembers and what it can automate.

Acceptance:

- User can configure memory behavior, browser automation permissions, connector permissions, and data retention.
- User can reset cloud memory.
- User can disable browser automation or connectors without deleting the account.

### Persistence

As a developer, I can persist Adele Web state in DynamoDB.

Acceptance:

- DynamoDB stores users, memory entries, task runs, task steps, approval requests, connector configs, browser sessions, and audit events.
- Data models use shared TypeScript schemas where possible.
- Local development can use mocked or local persistence before cloud deployment.

### Deployment

As a developer, I can deploy Adele Web to Vercel.

Acceptance:

- Web app runs locally.
- Web app builds.
- Required environment variables are documented.
- Vercel deployment path is documented.

## MVP Non-Goals

These are explicitly out of scope for the first Track B MVP:

- Native desktop control from Adele Web.
- Full parity with every Adele Desktop tool.
- Mobile app.
- Multi-user team workspaces.
- Enterprise admin console.
- Billing/subscriptions.
- Autonomous final submission without user approval.
- Unrestricted arbitrary code execution.
- Storing raw credentials in plaintext.
- Deep connector marketplace polish beyond a usable hackathon connector flow.

## Runtime Boundaries

### Web App

Owns UI, task state views, memory vault screens, approval queue, settings, and API routes.

### Agent Runtime

Owns planning, tool selection, connector calls, memory writes, browser action requests, and audit event creation.

### Chrome Extension

Owns active-tab observation and browser action execution. It should not own task planning or cloud memory.

### DynamoDB

Owns durable user, memory, task, approval, connector, browser session, and audit data.

### Shared Packages

Own schemas, typed contracts, and JSON-compatible data models used by the web app, extension, and later desktop integration.

## Initial Data Contracts

Track B should define shared schemas for:

- `User`
- `MemoryEntry`
- `TaskRun`
- `TaskStep`
- `Plan`
- `Milestone`
- `ApprovalRequest`
- `BrowserSession`
- `BrowserSnapshot`
- `BrowserElementRef`
- `BrowserAction`
- `BrowserActionResult`
- `ConnectorConfig`
- `ToolCall`
- `AuditEvent`
- `UserPreference`

## Product Architecture Target

```text
Adele Web UI (Next.js on Vercel)
  -> API routes / server actions
  -> Agent runtime
  -> Shared schemas
  -> DynamoDB persistence
  -> Connector adapter layer
  -> Browser extension bridge

Adele Web Chrome Extension
  -> Active tab snapshot
  -> Ref-based browser actions
  -> Action result reporting
```

## B0 Acceptance Criteria

B0 is complete when:

- Adele Web product definition is documented.
- MVP scope is explicit.
- Non-goals are explicit.
- Desktop vs web runtime boundary is explicit.
- Demo workflow is explicit.
- Product capabilities map to future Track B milestones.
- B1 can start without re-litigating what Adele Web is supposed to be.

## B0 Result

Status: Complete.

Track B can proceed to B1: scaffold `apps/web`.
