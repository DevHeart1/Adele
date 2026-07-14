# Adele Web Plan

Adele Web is the planned browser/cloud version of ADELE. It should provide the full Adele agent experience through web-native execution surfaces.

The canonical B0 product contract is documented in:

```text
B0_ADELE_WEB_PRODUCT_CONTRACT.md
```

See also:

```text
docs/web/PRODUCT_CONTRACT.md
```

## Product Scope

Adele Web should include:

- Chat and command interface.
- Cloud memory vault.
- Browser automation through a web Chrome extension.
- Task planning and action timeline.
- Approval queue for sensitive actions.
- Connector and MCP management.
- DynamoDB persistence.
- Vercel deployment.

## Planned Location

```text
apps/web/
apps/web-extension/
packages/shared/
packages/browser-automation/
packages/connectors/
```

## Execution Model

Desktop Adele controls the local computer. Adele Web controls web apps and connected cloud tools:

```text
Adele Web on Vercel
 -> Next.js API routes / agent runtime
 -> DynamoDB memory and task state
 -> Chrome extension for active-tab automation
 -> Composio/MCP connectors for external tools
```

## First Demo Workflow

The target hackathon demo is a job-application workflow:

1. Read a job listing from the active browser tab.
2. Compare it to saved user profile memory.
3. Save the listing to DynamoDB.
4. Fill safe application fields.
5. Draft application answers.
6. Stop before submit and ask for approval.
