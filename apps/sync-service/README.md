# sync-service

Syncs Azure DevOps work items into PostgreSQL, scoped per area path.

## Ownership

**This is the only service in the monorepo authorized to write to the
database** (INSERT / UPDATE / DELETE / UPSERT / operational data
migrations). See `docs/adr/0002-single-writer.md`.

Responsibilities:
- Poll Azure DevOps (WIQL + work item batch REST calls) per area path.
- Normalize and upsert work items, work item history, and checkpoints.
- Own the Postgres schema (`app/db.py`).

Consumers that need to read this data (future `api-read`, dashboards,
reports) must go through a read-only service — never connect directly to
this database from another app.

## Setup

1. Set Windows environment variables:
   - Put `DATABASE_URL` and `AZURE_DEVOPS_API_KEY` in the repository root `.env`.
   - `SQLITE_DATABASE_PATH` is optional and defaults to `apps/data/azure_sync.sqlite3`.
   - If PostgreSQL is not configured or cannot be reached, the service uses SQLite.
2. Install dependencies:
   ```powershell
   python -m pip install --user uv
   uv venv
   uv pip install --python .venv\Scripts\python.exe -r requirements.txt
   ```
3. Run:
   ```
   .\.venv\Scripts\Activate.ps1
   python .\run.py
   ```
4. Open http://127.0.0.1:5000

## Running tests

Requires a local Postgres test database:
```
createdb azure_sync_test
set TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/azure_sync_test
pytest
```

## Usage

- Add an area path via the form on the home page (organization, project, area path, include sub-paths, active, interval in minutes).
- First sync for a new area path is a full load; subsequent syncs are incremental and remove items no longer in scope.
- Click "Sincronizar agora" to trigger a sync manually — disabled while a sync is already running for that area path.
- A red banner appears at the top if any area path's last sync failed due to an invalid/expired token — check `AZURE_DEVOPS_API_KEY`.
