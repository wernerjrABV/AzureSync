# Work Item History Sync — Design

## Purpose

Track the full change history of every work item (card) synced from Azure DevOps, so users can see everything that happened to a card over time (state transitions, field changes, relation changes, who changed what and when) — not just its current snapshot.

## Data source

Azure DevOps Work Item Updates API: `GET /_apis/wit/workitems/{id}/updates`. Each entry is a diff between two revisions: the fields that changed (`oldValue`/`newValue`), who made the change (`revisedBy`), when (`revisedDate`), and the revision number (`rev`). This is preferred over the Revisions API (full snapshots) because it already expresses "what changed" without requiring us to diff consecutive snapshots ourselves.

## Schema changes

### New table: `work_item_history`

```sql
CREATE TABLE IF NOT EXISTS work_item_history (
    work_item_id INTEGER NOT NULL,
    area_path_id INTEGER NOT NULL REFERENCES area_paths(id),
    rev INTEGER NOT NULL,
    revised_by TEXT,
    revised_date TIMESTAMP,
    raw_json JSONB,
    synced_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (work_item_id, rev)
);
```

- One row per update entry (per revision), not per work item.
- `raw_json` stores the raw update payload (changed fields, relations, etc.) verbatim, following the same pattern as `work_items.raw_json`.
- `revised_by` and `revised_date` are extracted as columns for convenient sorting/filtering; everything else stays in `raw_json`.
- No foreign key to `work_items.id` — history rows must survive even if the parent work item is later deleted from `work_items` (e.g., it left the area path scope), since the history is still meaningful audit data.

### `area_paths`: new column

```sql
ALTER TABLE area_paths ADD COLUMN IF NOT EXISTS history_loaded_at TIMESTAMP;
```

`NULL` means the full historical backfill has not yet been completed for this area path. This is tracked separately from the existing `sync_checkpoints`/first-sync detection for `work_items`, because area paths that were already syncing work items before this feature existed have no history loaded yet, despite having a checkpoint.

## Data flow

In `sync_service._do_sync`, after resolving `current_ids` (all cards in scope) and `changed_ids` (delta since checkpoint):

- If `area_path_row["history_loaded_at"]` is `None`: this is the first history sync — target IDs for history sync = `current_ids` (every card in the area path).
- Otherwise: target IDs = `changed_ids` (only cards that changed in this sync cycle).
- For each target ID: call `client.get_work_item_updates(id)`, paginating with `$skip` until an empty page is returned, then `repo.upsert_work_item_history(conn, area_path_id, id, updates)`.
- If this was a first-time (full) history load and it completed without error, call `repo.set_history_loaded(conn, area_path_id, finished_at)`.

This runs after the existing full/delta work item sync logic; ordering relative to the work item upsert step doesn't matter functionally, but it will be placed after work item upserts and before checkpoint advancement for readability.

## API client changes (`ado_client.py`)

- New method `get_work_item_updates(self, work_item_id: int) -> list[dict]`.
- Calls `GET https://dev.azure.com/{org}/{project}/_apis/wit/workitems/{id}/updates?api-version=7.1&$top=100&$skip=N`.
- Requires a new `_get_with_retry` helper alongside the existing `_post_with_retry` (same retry/backoff/auth-error semantics, just a GET instead of a POST), since the Updates API is a GET endpoint.
- Loops incrementing `$skip` by 100 until a page returns zero items, accumulating all updates for that work item.
- The Updates API has no batch equivalent — one HTTP call (or more, if paginated) per work item, unlike `get_work_items_batch`'s 200-item batching.

## Repository changes (`repository.py`)

- `upsert_work_item_history(conn, area_path_id, work_item_id, updates: list[dict]) -> None` — upserts each update row keyed on `(work_item_id, rev)`, following the same `INSERT ... ON CONFLICT DO UPDATE` pattern as `upsert_work_items`.
- `set_history_loaded(conn, area_path_id, when) -> None` — sets `area_paths.history_loaded_at`.

## Error handling

No new error-handling mechanism is introduced. A failure in any history API call (e.g., retries exhausted, auth error) propagates as an exception and is caught by the existing `run_sync` try/except, which rolls back, records the error via `_fail`, and releases the lock — identical to how work item sync failures are already handled today.

Because all writes are idempotent (`upsert_work_item_history` upserts by `(work_item_id, rev)`, and `history_loaded_at` is only set after the full backfill completes without error), a sync that fails partway through simply re-fetches and re-upserts on the next cycle. No partial-progress tracking is needed.

## Testing

- `tests/test_ado_client.py`: `get_work_item_updates` pagination (multiple pages, empty-page termination) and retry/auth-error behavior via the new `_get_with_retry` helper.
- `tests/test_repository.py`: `upsert_work_item_history` upsert-by-`(work_item_id, rev)` semantics; `set_history_loaded`.
- `tests/test_sync_service.py`: first sync backfills history for all current IDs and sets `history_loaded_at`; subsequent syncs only fetch history for `changed_ids`; a failure during history sync leaves `history_loaded_at` unset and surfaces via the existing error path.

## Out of scope

- No UI/route changes for displaying history — this design covers only the sync/storage layer.
- No per-field normalization (e.g., separate rows per changed field) — `raw_json` holds the full diff payload; field-level queries can be added later by querying into the JSONB if needed.
