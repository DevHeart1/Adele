# Adele Web

Adele Web is the browser/cloud Adele product defined in `B0_ADELE_WEB_PRODUCT_CONTRACT.md`.

## Stack

- Next.js App Router
- TypeScript
- Tailwind CSS
- Zod
- AWS SDK v3
- Vercel target deployment

## Local Development

```powershell
npm --workspace apps/web run dev
```

## Build

```powershell
npm --workspace apps/web run build
```

## Route Groups

```text
src/app/(dashboard)
src/app/memory
src/app/tasks
src/app/connectors
src/app/browser
src/app/settings
```

## Environment

Copy `.env.example` to `.env.local` when local secrets are needed.
