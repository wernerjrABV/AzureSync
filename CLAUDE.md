# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app (http://127.0.0.1:5000)
python run.py

# Run tests (requires a local Postgres test DB)
createdb azure_sync_test
set TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/azure_sync_test
pytest

# Run a single test file / test
pytest tests/test_sync_service.py
pytest tests/test_sync_service.py::test_name -v
```

Required environment variables (Windows env vars, not a `.env` file):
- `DATABASE_URL` — Postgres connection string for the app's own DB.
- `TEST_DATABASE_URL` — separate Postgres DB used only by `tests/conftest.py`; tests are skipped if unset.
- `AZURE_DEVOPS_API_KEY` — Azure DevOps PAT used by `AdoClient`.

## Architecture

Flask app that polls Azure DevOps (via WIQL + work item batch REST calls) and syncs work items into Postgres, scoped per **area path**. Each area path is a row with its own schedule, lock, and checkpoint — the whole system is designed to run many of these concurrently and independently.

Module responsibilities (`app/`):
- `ado_client.py` — thin Azure DevOps REST wrapper. Handles auth (Basic w/ PAT), retries on 429/5xx with `Retry-After` support, and raises `AdoAuthError` (401) / `AdoRetryExhaustedError` (retries exhausted) so callers can distinguish failure modes. `get_changed_ids` uses **date precision, not datetime** in the WIQL `ChangedDate` filter (ADO rejects a time component) — re-fetching a whole day is intentional and safe because upserts are idempotent.
- `repository.py` — all SQL, using raw `psycopg` (no ORM). Every function takes a `conn` and does not commit; callers control transaction boundaries.
- `sync_service.run_sync` — orchestrates one sync for one area path:
  1. `try_acquire_lock` (DB-row-based lock via `is_running` flag) — returns `skipped_running` if another sync is in progress for that area path.
  2. Full ID list fetch (`get_all_ids`) + incremental changed-ID fetch since the stored checkpoint (`get_changed_ids`).
  3. Upserts changed items, then diffs current ADO IDs against stored IDs to delete items that left scope.
  4. Advances the checkpoint to the max `changed_date` seen.
  5. Always releases the lock in `finally`, and on any exception calls `_fail`, which **rolls back first** (a failed `_do_sync` can leave the transaction aborted) before writing the error status — this ordering matters, don't reorder it.
  - First sync for an area path is effectively a full load (no checkpoint yet); later syncs are incremental.
- `scheduler.py` — APScheduler background job ticking every minute; per-area-path due time is `last_sync_at + intervalo_minutos`, computed in Python (not via separate per-row jobs).
- `routes.py` — `create_app(conn_factory=...)` factory pattern; routes open a connection per request via the injectable `conn_factory` (this is how tests substitute a test DB — see `test_routes.py`). Manual sync endpoint returns 409 if a sync is already running.
- `db.py` — schema is defined as one `SCHEMA_SQL` string with `CREATE TABLE IF NOT EXISTS`; new columns are added via appended `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements rather than migration files.

### Schema relationships
`area_paths` (1) → `work_items`, `sync_checkpoints` (1:1), `sync_logs` (1:many), all keyed by `area_path_id`. `raw_json` on `work_items` stores the full ADO API response (all fields, including custom ones) even though only a few columns are projected out for querying.

### Failure surfacing
Sync failures are stored per-row (`last_sync_status`, `last_error_msg`) rather than raised to the UI as exceptions. `routes.py`'s index view flags `auth_error` specifically so the template can show a banner prompting the user to check `AZURE_DEVOPS_API_KEY`.
