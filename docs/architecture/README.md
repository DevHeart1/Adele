# ADELE Architecture Notes

ADELE is being migrated into a multi-surface monorepo.

## Surfaces

```text
Adele Desktop = local OS + browser automation
Adele Web     = cloud/browser/MCP automation
Shared Core   = schemas, protocols, memory/task models, browser actions
```

## Monorepo Layout

```text
apps/
  desktop/
  landing/
  web/
  web-extension/
packages/
  shared/
  agent-core/
  browser-automation/
  connectors/
infra/
  aws/
docs/
```

## Existing Diagrams

- [System Overview](../diagrams/01-system-overview.svg)
- [Agent Pipeline](../diagrams/02-agent-pipeline.svg)
- [Gemini Local Flow](../diagrams/03-gemini-local-flow.svg)

## Migration References

- [Implementation Plan](../../IMPLEMENTATION_PLAN.md)
- [A0 Baseline Audit](../../A0_BASELINE_AUDIT.md)
- [A1 Monorepo Layout](../../A1_MONOREPO_LAYOUT.md)
