# B2 Shared Schemas Report

Date: 2026-06-18

## Goal

Create `packages/shared` as the shared contract package for Adele Web, browser extensions, and future desktop/web interoperability.

## Completed

- Created `packages/shared`.
- Added TypeScript build configuration.
- Added Zod schemas for Track B shared contracts.
- Exported inferred TypeScript types.
- Added JSON-compatible schema design rules.
- Added tests that validate memory, task, approval, browser, connector, and preference contracts.

## Schemas Added

```text
User
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
AuditEvent
UserPreference
```

## Verification

```powershell
npm --workspace packages/shared run build
npm --workspace packages/shared run test
```

Result:

- `npm --workspace packages/shared run build`: pass.
- `npm --workspace packages/shared run test`: pass, 5 tests passed.
- Web can import from the shared workspace package in future milestones.

## Status

Complete.
