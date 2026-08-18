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
`http://127.0.0.1:5000`). Configure either URL with the Windows environment
variables `VITE_API_READ_BASE_URL` and `VITE_SYNC_SERVICE_BASE_URL` before
starting Vite.

## Capacity & Flow

The **Capacity & Flow** page reads the published snapshot from
`GET /api/capacity?area_path_id=<id>&year=<yyyy>&quarter=<1..4>`. A forecast
is unavailable until sync-service completes the area's first history backfill
and at least three months contain completed eligible work. Canceled items are
excluded; reopened items count only at their final completion.

Run the automated tests with:

```bash
npm test
```

## Portable Windows bundle notes

The portable Windows distribution does not run the Vite dev server. During
`.\scripts\build-portable.ps1`, this app is tested with `npm test`, built with
`npm run build`, and the static output is embedded into the packaged `api-read`
service that serves `http://127.0.0.1:5173`.

Portable operators should:

1. Extract `AzureSync-win-x64.zip` to a writable local folder.
2. Launch `AzureSync.exe`.
3. Save the Azure DevOps PAT from the Synchronization page.
4. Use `StopAzureSync.exe` before moving or deleting the extracted folder.

If startup fails, begin with `%LOCALAPPDATA%\AzureSync\logs\launcher-error.log`
and `%LOCALAPPDATA%\AzureSync\logs\api-read.stderr.log`. The packaged app uses
fixed loopback ports `5000` and `5173`, so it will not start if either is
already occupied.
