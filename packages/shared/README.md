# @adele/shared

Shared TypeScript and Zod contracts for Adele Web, browser extensions, and future desktop/web interoperability.

## Build

```powershell
npm --workspace packages/shared run build
```

## Test

```powershell
npm --workspace packages/shared run test
```

## Design Rules

- Schemas must be JSON-compatible.
- IDs are strings.
- Timestamps are ISO datetime strings.
- Runtime-specific objects such as DOM nodes, class instances, functions, and binary buffers do not belong in shared contracts.
- Schema names should stay compatible with the desktop Python concepts where practical.
