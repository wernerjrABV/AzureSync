# web-read

React 19 + TypeScript (Vite) frontend that lists work items through
`apps/api-read` and manages synchronization area paths through
`apps/sync-service`. **Never talks to the database directly.**

## Structure

- `src/models/` — TypeScript types mirroring `apps/api-read`'s JSON
  contracts (see `packages/shared-contracts/`).
- `src/services/apiReadClient.ts` — the typed client for api-read work-item
  and feature requests.
- `src/services/syncServiceClient.ts` — the typed client for sync-service
  area-path CRUD and manual synchronization requests.
- `src/pages/WorkItemsListPage.tsx` — the listing UI (filters, pagination,
  loading/empty/error states).

## Running

```bash
cd apps/web-read
npm install
npm run dev
```

Requires `apps/api-read` running (default `http://127.0.0.1:5001`).
For synchronization management, also run `apps/sync-service` (default
`http://127.0.0.1:5000`). Configure either URL via `.env` using
`VITE_API_READ_BASE_URL` and `VITE_SYNC_SERVICE_BASE_URL` (see
`.env.example`).

Run the automated tests with:

```bash
npm test
```
