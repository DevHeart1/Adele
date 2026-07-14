# B4 Web Persistence Layer Report

## Goal

Implement the Adele Web DynamoDB persistence layer so the web app can store and retrieve memory, task, approval, and connector records through the single-table model defined in B3.

## Completed

- Added a DynamoDB client factory and health checker.
- Added shared item helpers for put, get, delete, query, and update operations.
- Added key builders for Adele Web single-table entities.
- Added memory CRUD helpers.
- Added task run and task step CRUD helpers.
- Added approval CRUD helpers, including status updates.
- Added connector config CRUD helpers.
- Added `GET /api/health/aws` for DynamoDB table health.
- Added web persistence tests using fake DynamoDB clients.
- Connected `apps/web` to `@adele/shared` so persistence inputs are schema-validated.

## Verification

Completed from the repository root:

```powershell
npm install
npm --workspace apps/web run test
npm --workspace apps/web run typecheck
npm --workspace apps/web run build
```

Results:

- `npm install`: passed.
- `npm --workspace apps/web run test`: passed, 4 tests.
- `npm --workspace apps/web run typecheck`: passed.
- `npm --workspace apps/web run build`: passed.

For a live AWS check after credentials and the table are configured:

```powershell
curl http://localhost:3000/api/health/aws
```

Local route smoke check returned:

```json
{
  "ok": false,
  "region": "us-east-1",
  "tableName": "AdeleWeb",
  "error": "Could not load credentials from any providers"
}
```

## Notes

- The persistence tests do not require AWS credentials.
- The live health route requires `AWS_REGION`, AWS credentials, and `ADELE_DYNAMODB_TABLE`.
- Default table name remains `AdeleWeb` to match B3.
