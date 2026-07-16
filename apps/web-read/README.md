# web-read

React 19 + TypeScript (Vite) frontend that lists work items by calling
`apps/api-read`. **Never talks to the database directly and never calls
any backend other than `apps/api-read`.**

## Structure

- `src/models/` — TypeScript types mirroring `apps/api-read`'s JSON
  contracts (see `packages/shared-contracts/`).
- `src/services/apiReadClient.ts` — the only place that knows the api-read
  base URL or calls `fetch`.
- `src/pages/WorkItemsListPage.tsx` — the listing UI (filters, pagination,
  loading/empty/error states).

## Running

```bash
cd apps/web-read
npm install
npm run dev
```

Requires `apps/api-read` running (default `http://127.0.0.1:5001`).
Configure a different URL via `.env` (`VITE_API_READ_BASE_URL`, see
`.env.example`).

## Known gaps

No automated test suite is wired up yet (out of scope for this increment
per `docs/superpowers/specs/2026-07-15-read-path-design.md`).
