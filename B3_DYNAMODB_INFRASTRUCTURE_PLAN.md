# B3 DynamoDB Infrastructure Plan

Date: 2026-06-18

## Goal

Define AWS DynamoDB storage for Adele Web before implementing CRUD helpers.

## Completed

- Added DynamoDB architecture documentation.
- Defined the single-table key model.
- Defined `PK`, `SK`, `GSI1PK`, and `GSI1SK` patterns.
- Mapped B2 shared schema entities to DynamoDB item patterns.
- Added AWS environment variables to the web app example environment.
- Added an optional table creation script.
- Added setup and verification commands.

## Files

```text
docs/architecture/DYNAMODB.md
apps/web/scripts/create-dynamodb-table.mjs
apps/web/.env.example
apps/web/package.json
```

## Required Environment Variables

```text
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
ADELE_DYNAMODB_TABLE=AdeleWeb
```

## Verification

Schema/script validation:

```powershell
npm --workspace apps/web run typecheck
npm --workspace apps/web run build
node --check apps/web/scripts/create-dynamodb-table.mjs
```

Result:

- Typecheck: pass.
- Build: pass.
- Table creation script syntax check: pass.

AWS verification after credentials/table creation:

```powershell
npm --workspace apps/web run db:create-table
aws dynamodb describe-table --table-name AdeleWeb --region us-east-1
```

## Status

Complete for infrastructure planning. AWS table creation requires credentials and was not run by default.
