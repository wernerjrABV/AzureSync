# Work Item Details Drawer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add complete work-item detail retrieval and an Astryx right-side drawer opened by clicking a row in the Work Items screen.

**Architecture:** Add one read-only detail endpoint that joins the current item with its ordered history. The frontend keeps the paginated list unchanged, fetches detail on selection, and renders current fields, raw JSON, and history in the existing Astryx `Dialog` drawer pattern.

**Tech Stack:** Flask, psycopg/PostgreSQL, React 19, TypeScript, Vite/Vitest, `@astryxdesign/core`.

## Global Constraints

- `apps/sync-service/` remains the only database writer.
- `apps/api-read/app/repository.py` may issue SELECT queries only.
- `create_app(conn_factory=...)` remains the request-scoped DB test hook.
- Use Astryx components exclusively; do not add custom CSS when Astryx composition is sufficient.
- Preserve existing list pagination, search, ordering, and Feature Roadmap behavior.
- Use TDD: each behavior gets a failing test before production code.

---

### Task 1: Add repository detail queries

**Files:**
- Modify: `apps/api-read/app/repository.py`
- Test: `apps/api-read/tests/test_repository.py`

**Interfaces:**
- Produce `get_work_item_details(conn, *, work_item_id: int) -> dict | None`.
- Return `{"item": <current row>, "history": [<revision rows>]}` or `None` when no current row exists.

- [ ] Write tests that seed a current item and two history revisions, assert all current columns including `raw_json`, all history columns, and ascending `rev`; add a missing-ID test.
- [ ] Run `cd apps/api-read; pytest tests/test_repository.py::test_get_work_item_details -v` and confirm the new tests fail because the function is absent.
- [ ] Implement two parameterized SELECT queries: current `work_items` row with all detail columns, then `work_item_history WHERE work_item_id = %s ORDER BY rev ASC`; return the specified envelope.
- [ ] Run the focused repository tests and confirm they pass, then run `pytest tests/test_repository.py -q`.
- [ ] Commit with `git add apps/api-read/app/repository.py apps/api-read/tests/test_repository.py; git commit -m "feat(api-read): query complete work item details"`.

### Task 2: Expose the detail route

**Files:**
- Modify: `apps/api-read/app/routes.py`
- Test: `apps/api-read/tests/test_routes.py`

**Interfaces:**
- Produce `GET /api/work-items/<int:work_item_id>` returning `{"data": {"item": ..., "history": [...]}}` with status 200, or `{"error": "work item not found"}` with status 404.

- [ ] Add route tests for the 200 envelope and missing-item 404 using the existing `create_app(conn_factory=lambda: db_conn)` fixture; run them and observe failure because the route is absent.
- [ ] Add the route, obtain a connection through `conn_factory`, call `repo.get_work_item_details`, and map `None` to 404.
- [ ] Run `cd apps/api-read; pytest tests/test_routes.py::test_get_work_item_details tests/test_routes.py::test_get_work_item_details_not_found -v`, then run the complete API test suite.
- [ ] Commit with `git add apps/api-read/app/routes.py apps/api-read/tests/test_routes.py; git commit -m "feat(api-read): expose work item details route"`.

### Task 3: Add typed frontend detail client

**Files:**
- Modify: `apps/web-read/src/models/workItem.ts`
- Modify: `apps/web-read/src/services/apiReadClient.ts`
- Test: `apps/web-read/src/services/apiReadClient.test.ts`

**Interfaces:**
- Produce `WorkItemDetails`, `WorkItemHistoryRevision`, and `fetchWorkItemDetails(id: number): Promise<WorkItemDetails>`.

- [ ] Write a client test that stubs `fetch`, calls `fetchWorkItemDetails(42)`, asserts `/api/work-items/42`, and verifies the parsed response; run it and confirm failure.
- [ ] Add the TypeScript models for all current and history fields, allowing nullable values and JSON payloads as `unknown`.
- [ ] Implement the GET client with `response.ok` validation matching existing client functions.
- [ ] Run `cd apps/web-read; npm test -- src/services/apiReadClient.test.ts` and then `npm run build`.
- [ ] Commit the models, client, and test.

### Task 4: Add row selection and drawer UI

**Files:**
- Modify: `apps/web-read/src/pages/WorkItemsListPage.tsx`
- Test: `apps/web-read/src/pages/WorkItemsListPage.test.tsx` (create if no page test exists)

**Interfaces:**
- Clicking a table row selects its ID, fetches detail, and opens the drawer.
- Drawer displays current fields, `JSON.stringify(raw_json, null, 2)`, and every revision's metadata/payload using Astryx `Dialog`, `DialogHeader`, `VStack`, `Text`, `Banner`, and `Spinner`.

- [ ] Add a page test for clicking a row, showing the detail spinner, then rendering title/current fields, raw JSON, and both history revisions; add a failed-detail test asserting the error banner. Use only unavoidable network stubs and existing test setup patterns.
- [ ] Run the focused page test and confirm it fails before implementation.
- [ ] Add selected-item/detail state and a request ID ref so stale responses cannot replace newer selection state; invoke `fetchWorkItemDetails` from the row click handler.
- [ ] Configure the Astryx `Dialog` with `isOpen={selectedItemId !== null}`, right-edge full-height positioning, and `DialogHeader` close behavior, matching `GanttChart.tsx`.
- [ ] Add readable detail sections with null fallback `—`, formatted JSON, and history ordered as returned. Do not add a custom stylesheet; use existing Astryx layout components and safe text rendering.
- [ ] Run the focused page test, then `npm run build` and the full web test suite.
- [ ] Commit with `git add apps/web-read/src/pages/WorkItemsListPage.tsx apps/web-read/src/pages/WorkItemsListPage.test.tsx; git commit -m "feat(web-read): show work item details drawer"`.

### Task 5: Full verification

**Files:**
- Verify: `apps/api-read/`, `apps/web-read/`

- [ ] Run `cd apps/api-read; pytest -q` with `TEST_DATABASE_URL` configured; confirm all tests pass.
- [ ] Run `cd apps/web-read; npm test`; confirm all tests pass.
- [ ] Run `cd apps/web-read; npm run build`; confirm TypeScript and Vite build pass.
- [ ] Run `git diff --check` and inspect `git status --short`; confirm only intended changes remain and no custom CSS or write SQL was introduced.
