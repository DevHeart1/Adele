# Adele Web DynamoDB Infrastructure Plan

Date: 2026-06-18

## Goal

Define the DynamoDB structure for Adele Web before CRUD helpers are implemented in B4.

## Table

```text
Table: AdeleWeb
Partition key: pk (String)
Sort key: sk (String)

GSI1 partition key: gsi1pk (String)
GSI1 sort key: gsi1sk (String)
```

## Environment Variables

```text
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
ADELE_DYNAMODB_TABLE=AdeleWeb
```

For local development, credentials can come from normal AWS SDK resolution instead of `.env.local`: environment variables, AWS profile, or an attached role in deployed infrastructure.

## Entity Key Patterns

| Entity | PK | SK | GSI1PK | GSI1SK |
| --- | --- | --- | --- | --- |
| User profile | `USER#{userId}` | `PROFILE#default` | `ENTITY#USER` | `UPDATED#{updatedAt}#USER#{userId}` |
| Memory entry | `USER#{userId}` | `MEMORY#{memoryId}` | `USER#{userId}#MEMORY#{category}` | `UPDATED#{updatedAt}#MEMORY#{memoryId}` |
| Task run | `USER#{userId}` | `TASK#{taskId}` | `USER#{userId}#TASK#{status}` | `UPDATED#{updatedAt}#TASK#{taskId}` |
| Task step | `USER#{userId}` | `TASK#{taskId}#STEP#{stepId}` | `TASK#{taskId}#STEP` | `INDEX#{index}#STEP#{stepId}` |
| Plan | `USER#{userId}` | `TASK#{taskId}#PLAN#{planId}` | `TASK#{taskId}#PLAN` | `CREATED#{createdAt}#PLAN#{planId}` |
| Milestone | `USER#{userId}` | `TASK#{taskId}#MILESTONE#{milestoneId}` | `TASK#{taskId}#MILESTONE` | `CREATED#{createdAt}#MILESTONE#{milestoneId}` |
| Approval request | `USER#{userId}` | `APPROVAL#{approvalId}` | `USER#{userId}#APPROVAL#{status}` | `CREATED#{createdAt}#APPROVAL#{approvalId}` |
| Connector config | `USER#{userId}` | `CONNECTOR#{connectorId}` | `USER#{userId}#CONNECTOR#{provider}` | `UPDATED#{updatedAt}#CONNECTOR#{connectorId}` |
| Browser session | `USER#{userId}` | `BROWSER_SESSION#{sessionId}` | `USER#{userId}#BROWSER_SESSION` | `UPDATED#{updatedAt}#SESSION#{sessionId}` |
| Browser snapshot | `USER#{userId}` | `BROWSER_SESSION#{sessionId}#SNAPSHOT#{snapshotId}` | `SESSION#{sessionId}#SNAPSHOT` | `GEN#{generation}#SNAPSHOT#{snapshotId}` |
| Browser action | `USER#{userId}` | `BROWSER_SESSION#{sessionId}#ACTION#{actionId}` | `SESSION#{sessionId}#ACTION` | `CREATED#{createdAt}#ACTION#{actionId}` |
| Browser action result | `USER#{userId}` | `BROWSER_SESSION#{sessionId}#ACTION_RESULT#{actionId}` | `SESSION#{sessionId}#ACTION_RESULT` | `COMPLETED#{completedAt}#ACTION#{actionId}` |
| Tool call | `USER#{userId}` | `TASK#{taskId}#TOOL_CALL#{toolCallId}` | `TASK#{taskId}#TOOL_CALL` | `STARTED#{startedAt}#TOOL_CALL#{toolCallId}` |
| Audit event | `USER#{userId}` | `AUDIT#{createdAt}#{auditEventId}` | `TASK#{taskId}#AUDIT` | `CREATED#{createdAt}#AUDIT#{auditEventId}` |
| Preferences | `USER#{userId}` | `PREFERENCES#default` | `ENTITY#PREFERENCES` | `UPDATED#{updatedAt}#USER#{userId}` |

## Item Shape

Every item should include:

```ts
{
  pk: string;
  sk: string;
  gsi1pk?: string;
  gsi1sk?: string;
  entityType: string;
  version: 1;
  createdAt: string;
  updatedAt?: string;
  data: JsonValue;
}
```

The `data` payload should validate against the relevant `@adele/shared` Zod schema before writes and after reads.

## Access Patterns

### User Home

Query:

```text
PK = USER#{userId}
```

Use this for loading the user profile, recent tasks, memory summaries, approvals, connectors, and preferences.

### Memory Vault

Query by user and category:

```text
GSI1PK = USER#{userId}#MEMORY#{category}
```

Sort descending by `gsi1sk` to show most recently updated memory first.

### Task Timeline

Query:

```text
PK = USER#{userId}
SK begins_with TASK#{taskId}
```

Returns the task run, plan, milestones, steps, and tool calls for one task.

### Pending Approvals

Query:

```text
GSI1PK = USER#{userId}#APPROVAL#pending
```

Sort ascending by `gsi1sk` to handle oldest pending approvals first.

### Connector List

Query:

```text
PK = USER#{userId}
SK begins_with CONNECTOR#
```

### Browser Session State

Query:

```text
PK = USER#{userId}
SK begins_with BROWSER_SESSION#{sessionId}
```

Returns session metadata, snapshots, queued actions, and action results.

### Audit By Task

Query:

```text
GSI1PK = TASK#{taskId}#AUDIT
```

Sort by `gsi1sk` for chronological audit event review.

## Capacity And Billing

Use on-demand billing for the MVP:

```text
BillingMode: PAY_PER_REQUEST
```

This avoids capacity planning during the hackathon phase.

## Retention

Recommended TTL attribute:

```text
expiresAt
```

Use TTL for browser snapshots, transient browser actions, and old audit/debug events. Do not apply TTL to user-approved memory unless the user configures retention.

## Security Notes

- Do not store raw connector secrets in DynamoDB.
- Store connector references, scopes, redacted labels, and encrypted secret handles only.
- Redact sensitive values in audit event summaries.
- Approval payloads should contain only the minimum data needed for user review.
- All writes should be scoped by `userId`.

## Creation Command

```powershell
npm --workspace apps/web run db:create-table
```

This reads:

```text
AWS_REGION
ADELE_DYNAMODB_TABLE
```

## Verification Command

```powershell
aws dynamodb describe-table --table-name AdeleWeb --region us-east-1
```

For the hackathon submission, a screenshot of the DynamoDB table details can prove AWS Database usage.
