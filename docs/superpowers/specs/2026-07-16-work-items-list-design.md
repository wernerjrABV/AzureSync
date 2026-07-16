# Work Items List: required area path, unified search, display-name Assigned To

## Problem

The work items list (`apps/web-read`, backed by `apps/api-read`) currently:

- Lets the area path filter be empty (shows all items across all area paths).
- Has a dedicated `work_item_type` text filter, separate from any other search.
- Stores `assigned_to` as the ADO `uniqueName` (email), not the person's display name.
- Has no way to search across ID, Title, Type, State, and Assigned To at once.

## Requirements

- Work items list ordered by Changed Date, newest first (already the default — no change).
- Columns shown: ID, Title, Type, State, Assigned To (**display name only**, not email), Changed Date.
- Area path filter is **required**; the UI always starts with the first area path in the list selected.
- A single search field filters across ID, Title, Type, State, and Assigned To (not Changed Date).
- Search is applied server-side (SQL), not client-side over the current page, so it works correctly with pagination.
- The dedicated Type filter is removed — the unified search field replaces it.
- `/api/work-items` requires `area_path_id`; the API rejects requests without it (400), matching the UI rule.

## Changes

### 1. `apps/sync-service/app/ado_client.py`

`_map_work_item` currently reads:

```python
assigned_to = assigned_to_field.get("uniqueName")
```

Change to read `displayName` instead:

```python
assigned_to = assigned_to_field.get("displayName")
```

No schema change — `assigned_to` stays `TEXT` in `work_items`.

### 2. One-off backfill script

New script, e.g. `apps/sync-service/scripts/backfill_assigned_to_display_name.py`:

- Connects to the DB directly (reuse `DATABASE_URL` / `app.db` connection helper).
- Selects `id, raw_json` from `work_items` where `raw_json` is not null.
- For each row, parses `raw_json`, reads `fields["System.AssignedTo"]["displayName"]` (guard for missing/None field — unassigned items).
- If the extracted display name differs from the current `assigned_to` value, runs `UPDATE work_items SET assigned_to = %s WHERE id = %s`.
- Commits in batches (reuse the same batching pattern as `HISTORY_COMMIT_BATCH_SIZE` if convenient, otherwise a simple fixed batch size) to bound transaction length on large tables.
- No calls to the ADO API — this is purely a local data migration since `raw_json` already contains the original payload.
- Run manually once, after deploying the `ado_client.py` change.

### 3. `apps/api-read/app/repository.py`

`list_work_items`:

- `area_path_id` becomes a required, non-optional parameter. If `None`, raise `InvalidQueryParam("area_path_id is required")`.
- Remove the `work_item_type` parameter entirely.
- Add a new optional `search: str | None` parameter. When present (non-empty after `.strip()`), add a clause:

```sql
AND (
    id::text ILIKE %s
    OR title ILIKE %s
    OR work_item_type ILIKE %s
    OR state ILIKE %s
    OR assigned_to ILIKE %s
)
```

  with the same `%<search>%` value bound five times. This clause is ANDed with the mandatory `area_path_id = %s` clause.

### 4. `apps/api-read/app/routes.py`

`list_work_items` route:

- Read `search = request.args.get("search")`.
- Remove `work_item_type` arg reading.
- Since `area_path_id` is now required by the repository layer, the existing `except repo.InvalidQueryParam` handler already surfaces the 400 — no separate route-level check needed, but confirm the error message is clear (`"area_path_id is required"`).

### 5. `apps/web-read/src/services/apiReadClient.ts`

`WorkItemListParams`:

- Replace `workItemType?: string` with `search?: string`.
- `areaPathId` stays optional in the TS type (the page component guarantees it's set before calling `fetchWorkItems`, but the client itself doesn't need to enforce it).

`fetchWorkItems`:

- Replace the `work_item_type` query param with `search` (only set when non-empty).

### 6. `apps/web-read/src/pages/WorkItemsListPage.tsx`

- After `fetchAreaPaths()` resolves, if `areaPathId` is still `undefined` and the list is non-empty, set `areaPathId` to `areaPaths[0].id`.
- Remove the `workItemType` state, the `TextInput label="Type"` filter, and its handling in the `fetchWorkItems` effect.
- Add a `search` state (`string`, default `""`) and a single `TextInput label="Search"` (with `hasClear`) that updates `search` and resets `page` to 1 on change.
- `Selector` for Area Path: remove `hasClear` and the `placeholder="All"` (there is no "unset" state once area paths have loaded); keep `hasSearch`.
- The work-items fetch effect should not run until `areaPathId` is defined (guard at the top of the effect, or condition the effect's dependency/skip logic) — while area paths are still loading, show the existing `Spinner`.

## Non-goals

- No change to `work_item_history` or any other sync-service behavior beyond the `assigned_to` field mapping.
- No change to pagination, ordering options, or the Changed Date column format.
- No retroactive re-sync via the ADO API — the backfill is purely local (`raw_json` → column).

## Testing

- `apps/api-read`: extend/add tests for `list_work_items` — missing `area_path_id` raises `InvalidQueryParam`; `search` matches against id/title/type/state/assigned_to independently and in combination with `area_path_id`.
- `apps/sync-service`: extend the existing `ado_client` mapping test (if present) to assert `assigned_to` now reads `displayName`.
- Backfill script: manual run against a local/test DB is acceptable; a small unit test around the extraction function (raw_json → display name) is a nice-to-have but not required.
