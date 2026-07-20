# Web Synchronization Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move complete area-path and manual synchronization management from the `:5000` HTML screen into the Astryx-based `web-read` application.

**Architecture:** `sync-service` remains the only database writer and exposes JSON management endpoints. `web-read` calls those endpoints directly through `VITE_SYNC_SERVICE_BASE_URL`, starts syncs asynchronously, and polls area-path status until completion. `api-read` remains read-only.

**Tech Stack:** Flask, psycopg/SQLite fallback, Python pytest, React 19, TypeScript, Vite, Vitest, Testing Library, Astryx Design System.

## Global Constraints

- `apps/sync-service/` is the only database writer.
- `repository.py` is the only file that issues write SQL.
- `sync_service.run_sync` owns locking, checkpoint advancement, upserts, deletes, and history backfill.
- On sync failure, roll back before writing error status.
- The web UI must use exclusively Astryx components; do not add custom CSS, inline styles, styled-components, emotion, or custom style sheets.
- Preserve existing Work Items and Features Roadmap behavior.
- Preserve unrelated existing working-tree changes; commit only files belonging to this feature.

---

### Task 1: Define the sync-service JSON contracts and response serialization

**Files:**
- Modify: `apps/sync-service/app/routes.py`
- Modify: `apps/sync-service/tests/test_routes.py`
- Modify: `apps/sync-service/app/repository.py` only if a small read helper is needed; keep all SQL there

**Interfaces:**
- Produces JSON `GET /api/area-paths` returning `{ "data": AreaPathStatus[] }`.
- Produces `POST /api/area-paths`, `PUT /api/area-paths/<int:id>`, and `DELETE /api/area-paths/<int:id>`.
- Produces `POST /api/area-paths/<int:id>/sync` with `202 {"status":"started"}` or `409`/`404` JSON errors.
- `AreaPathStatus` contains `id`, configuration fields, and all sync status fields required by the web.

- [ ] **Step 1: Write failing route tests**

Add tests asserting JSON list shape, create/update/delete request bodies, validation of empty fields and non-positive intervals, `404` for an unknown ID, and `409` when `is_running` is already true. For the sync route, patch the future/background launcher boundary and assert it receives a fresh area-path row and returns `202` without running `run_sync` in the request.

- [ ] **Step 2: Run the route tests and verify the expected failures**

Run `cd apps/sync-service; pytest tests/test_routes.py -v`. Expected: the new JSON tests fail because the endpoints and response serializer do not exist yet; existing HTML tests remain useful compatibility evidence until the old UI is removed in Task 5.

- [ ] **Step 3: Implement the minimal JSON routes**

Add a private serializer in `routes.py` that converts repository rows to JSON-safe values, including ISO formatting for timestamps and `None` for absent values. Parse JSON request bodies, validate `organization`, `project`, and `area_path`, and require `intervalo_minutos > 0`. Reuse `repo.create_area_path`, `repo.update_area_path`, `repo.delete_area_path`, `repo.list_area_paths`, and `repo.get_area_path`; commit successful mutations and return `400` for invalid payloads.

- [ ] **Step 4: Run focused tests and then the full sync-service route suite**

Run `cd apps/sync-service; pytest tests/test_routes.py -v`. Expected: all new JSON tests pass and the pre-existing behavior is still green before the async implementation is finalized.

- [ ] **Step 5: Commit the API contract slice**

Run `git add apps/sync-service/app/routes.py apps/sync-service/tests/test_routes.py; git commit -m "feat: add area path management API"`.

### Task 2: Make manual synchronization non-blocking and connection-safe

**Files:**
- Modify: `apps/sync-service/app/routes.py`
- Modify: `apps/sync-service/tests/test_routes.py`
- Modify: `apps/sync-service/app/scheduler.py` only if the shared runner is extracted there

**Interfaces:**
- Produces an internal `start_manual_sync(conn_factory, area_path_id) -> bool` launcher boundary, patched directly by route tests.
- Background worker opens its own request-independent connection, reloads the row, calls `AdoClient(row["organization"], row["project"])`, invokes `sync_service.run_sync`, and closes SQLite connections in `finally`.

- [ ] **Step 1: Add a failing test proving the request returns before sync completion**

Patch the launcher with a callable that records the area ID and does not execute the sync. Assert `POST /api/area-paths/<id>/sync` returns `202`, the launcher is called once, and the request connection is not passed into the worker.

- [ ] **Step 2: Run the focused test and verify it fails for the synchronous implementation**

Run `cd apps/sync-service; pytest tests/test_routes.py -k "async\|background\|json" -v`. Expected: failure showing the current route still performs work in the request or has no launcher.

- [ ] **Step 3: Implement a bounded background executor**

Use a module-level `ThreadPoolExecutor` with a small fixed worker count. The route must check the current row before submission, submit the worker with `conn_factory` and `area_path_id`, and return `202`. The worker opens a new connection, reloads the row, rechecks `is_running` to avoid duplicate work, runs the existing sync pipeline, commits/rolls back according to the pipeline contract, and closes SQLite connections. Do not move SQL into the route.

- [ ] **Step 4: Verify success, failure, and duplicate-start behavior**

Run `cd apps/sync-service; pytest tests/test_routes.py tests/test_sync_service.py -v`. Expected: the API returns immediately, duplicate starts return `409`, and existing rollback/status tests remain green.

- [ ] **Step 5: Commit the async execution slice**

Run `git add apps/sync-service/app/routes.py apps/sync-service/tests/test_routes.py apps/sync-service/app/scheduler.py; git commit -m "feat: start manual syncs in background"`.

### Task 3: Add the web sync-service client and configuration

**Files:**
- Create: `apps/web-read/src/services/syncServiceClient.ts`
- Create: `apps/web-read/src/services/syncServiceClient.test.ts`
- Modify: `apps/web-read/.env.example`
- Modify: `apps/web-read/README.md`

**Interfaces:**
- Produces `fetchSyncAreaPaths(): Promise<SyncAreaPath[]>`.
- Produces `createSyncAreaPath(input): Promise<SyncAreaPath>`.
- Produces `updateSyncAreaPath(id, input): Promise<SyncAreaPath>`.
- Produces `deleteSyncAreaPath(id): Promise<void>`.
- Produces `startAreaPathSync(id): Promise<void>`.
- Uses `const BASE_URL = import.meta.env.VITE_SYNC_SERVICE_BASE_URL ?? "http://127.0.0.1:5000"`.

- [ ] **Step 1: Write failing client tests**

Use the existing fetch-mocking style to assert HTTP method, URL, JSON body, and rejection on non-2xx responses for every operation. Include timestamp strings and nullable error/status fields in the `SyncAreaPath` fixture.

- [ ] **Step 2: Run the client tests and verify they fail**

Run `cd apps/web-read; npm test -- src/services/syncServiceClient.test.ts`. Expected: module/functions are missing.

- [ ] **Step 3: Implement the typed client**

Define `SyncAreaPath` and `AreaPathInput`, centralize `fetch` error handling, set `Content-Type` only for JSON bodies, parse `data` responses, and return useful status errors. Keep this client separate from `apiReadClient.ts` so read-only and write-capable contracts cannot be confused.

- [ ] **Step 4: Run the client tests and TypeScript build**

Run `cd apps/web-read; npm test -- src/services/syncServiceClient.test.ts; npm run build`. Expected: focused tests pass and the build exits successfully.

- [ ] **Step 5: Commit the web client slice**

Run `git add apps/web-read/src/services/syncServiceClient.ts apps/web-read/src/services/syncServiceClient.test.ts apps/web-read/.env.example apps/web-read/README.md; git commit -m "feat: add sync management client"`.

### Task 4: Build the Astryx Synchronization page with CRUD and polling

**Files:**
- Create: `apps/web-read/src/pages/SynchronizationPage.tsx`
- Create: `apps/web-read/src/pages/SynchronizationPage.test.tsx`
- Modify: `apps/web-read/src/App.tsx`

**Interfaces:**
- Consumes all functions from `syncServiceClient.ts`.
- Produces a page with loading, empty, error, CRUD, sync-running, success, auth-error, and generic-error states.

- [ ] **Step 1: Write failing page tests**

Render inside the existing `Theme`/neutral theme test wrapper. Test that the page lists area paths, opens the Astryx `Dialog` for create/edit, submits JSON-equivalent values, confirms deletion, disables the sync action while running, calls `startAreaPathSync`, polls with timers, and displays final `ok`, `auth_error`, and generic error messages. Do not assert custom class names or custom CSS.

- [ ] **Step 2: Run the page tests and verify they fail**

Run `cd apps/web-read; npm test -- src/pages/SynchronizationPage.test.tsx`. Expected: page module is missing.

- [ ] **Step 3: Implement the page using only Astryx components**

Use existing Astryx `Card`, `HStack`, `VStack`, `Text`, `TextInput`, `Selector`, `Dialog`, `DialogHeader`, `Banner`, `Badge`, `Spinner`, `EmptyState`, and any existing Astryx button/input components confirmed by package exports. Keep form state local, reuse one modal for create/edit, use native labels only where wrapped by Astryx input APIs require them, and use `window.confirm` only for deletion confirmation if Astryx has no confirmation component. Do not create CSS.

- [ ] **Step 4: Implement polling with cleanup**

After a successful start, track the area ID in a `Set`, refresh immediately, and schedule `setInterval`/timeout polling. Stop polling when `is_running` is false, on unmount, or after the request errors. Ensure stale polling responses cannot overwrite newer list state.

- [ ] **Step 5: Add the navigation item and render branch**

Extend `Page` in `App.tsx` with `"synchronization"`, add a selected Astryx `SideNavItem` with an existing sync/settings icon, and render `SynchronizationPage` without changing the existing page branches.

- [ ] **Step 6: Run focused page tests and build**

Run `cd apps/web-read; npm test -- src/pages/SynchronizationPage.test.tsx; npm run build`. Expected: all page tests pass and no custom style/build errors occur.

- [ ] **Step 7: Commit the Astryx UI slice**

Run `git add apps/web-read/src/pages/SynchronizationPage.tsx apps/web-read/src/pages/SynchronizationPage.test.tsx apps/web-read/src/App.tsx; git commit -m "feat: add Astryx synchronization page"`.

### Task 5: Retire the old HTML management screen and update documentation

**Files:**
- Modify: `apps/sync-service/app/routes.py`
- Delete or stop serving: `apps/sync-service/app/templates/index.html`
- Delete or stop serving: `apps/sync-service/app/templates/area_path_form.html`
- Delete: `apps/sync-service/app/static/css/style.css` after confirming no remaining route references the retired templates
- Modify: `apps/sync-service/tests/test_routes.py`
- Modify: `apps/sync-service/README.md`
- Modify: `README.md`
- Modify: `scripts/run-all.ps1` and `scripts/run-all.cmd` only if startup docs still describe `:5000` as a UI

**Interfaces:**
- `:5000` is documented as the sync API/service, not the management UI.
- JSON routes remain available; HTML form routes are no longer required.

- [ ] **Step 1: Write a failing regression test for the retired UI contract**

Replace HTML index expectations with an assertion that `GET /` returns `404`, while JSON routes remain available.

- [ ] **Step 2: Run the route tests and verify the old HTML expectation fails**

Run `cd apps/sync-service; pytest tests/test_routes.py -v`. Expected: the old root/template assertions fail until the route and tests are updated together.

- [ ] **Step 3: Remove the old management routes/templates safely**

Delete only the HTML CRUD routes, both retired templates, and `style.css`. Keep the service process, JSON API, scheduler, health behavior if present, and all sync logic. Update README instructions from “open `http://127.0.0.1:5000`” to “open the web app; `:5000` is the sync API.”

- [ ] **Step 4: Run backend and frontend suites**

Run `cd apps/sync-service; pytest -v`; then `cd apps/web-read; npm test; npm run build`. Expected: all available tests pass; database-backed tests may follow the repository’s documented `TEST_DATABASE_URL` skip behavior.

- [ ] **Step 5: Commit the retirement/documentation slice**

Run `git add apps/sync-service/app/routes.py apps/sync-service/app/templates apps/sync-service/app/static/css/style.css apps/sync-service/tests/test_routes.py apps/sync-service/README.md README.md scripts/run-all.ps1 scripts/run-all.cmd; git commit -m "feat: retire sync service HTML management screen"`.

### Task 6: Final verification and architecture guardrails

**Files:**
- Modify: relevant tests/docs only if verification exposes a concrete mismatch

- [ ] **Step 1: Check the complete diff and repository status**

Run `git diff main...HEAD --stat`, `git diff --check`, and `git status --short`. Confirm unrelated pre-existing changes remain untouched and only feature commits contain feature files.

- [ ] **Step 2: Run the complete available verification**

Run `cd apps/sync-service; pytest -v`; `cd apps/api-read; pytest -v`; and `cd apps/web-read; npm test; npm run build`. Record skipped database tests separately from failures.

- [ ] **Step 3: Run the write-path guardrail**

Run the existing `apps/api-read/tests/test_readonly_guardrail.py` as part of the API suite and inspect changed Python files with `rg -n "INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE" apps/api-read`. Confirm no write SQL was introduced outside the sync-service repository.

- [ ] **Step 4: Review acceptance criteria**

Manually map each of the six criteria in the design spec to a tested implementation: CRUD, non-blocking start, polling result, single writer, retired HTML UI, and Astryx-only interface. If a criterion lacks evidence, report it rather than claiming completion.

- [ ] **Step 5: Commit only verification-related corrections**

If the previous steps require a concrete correction, add its test first, verify red/green, then commit it with a focused message. Do not amend unrelated user commits.
