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
   - Set `DATABASE_URL` in the Windows environment.
   - `SQLITE_DATABASE_PATH` is optional and defaults to `apps/data/azure_sync.sqlite3`.
   - If PostgreSQL is not configured or cannot be reached, the service uses SQLite.
   - Azure DevOps credentials are configured after startup in the web application:
     open Synchronization, enter the Azure DevOps personal access token in Azure
     DevOps credential, and choose Save credential. The token is encrypted for the
     current Windows user and is not stored in `.env`.
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

## Portable Windows bundle notes

The portable launcher starts sync-service from `portable_run.py` with
Waitress on the fixed loopback port `127.0.0.1:5000`. In portable mode it uses
SQLite only; the launcher sets `DATABASE_URL` empty and points
`SQLITE_DATABASE_PATH` to `%LOCALAPPDATA%\AzureSync\data\azure_sync.sqlite3`.

The portable operator flow is:

1. Extract `AzureSync-win-x64.zip` to a writable local folder.
2. Run `AzureSync.exe`.
3. Open Synchronization in the browser and save the Azure DevOps PAT.
4. Use `StopAzureSync.exe` before moving or deleting the extracted folder.

Logs are written under `%LOCALAPPDATA%\AzureSync\logs`. Startup failures are
reported through `%LOCALAPPDATA%\AzureSync\logs\launcher-error.log`; service
stderr is captured in `sync-service.stderr.log`.

The PAT is encrypted with Windows DPAPI for the current Windows user before it
is stored in SQLite. Copying the SQLite file to another Windows user does not
allow that user to decrypt the credential.

## Running tests

Requires a local Postgres test database:
```powershell
createdb azure_sync_test
$env:TEST_DATABASE_URL='postgresql://postgres:postgres@localhost:5432/azure_sync_test'
pytest
```

## Portable build prerequisites

The Windows bundle is produced from the repo root with:

```powershell
.\scripts\build-portable.ps1
```

Build hosts must be Windows x64 with Python x64 3.12+ and Node x64 22+.
Optional signing is supported with `-SignToolPath` and
`-CertificateThumbprint`. The root README documents the artifact paths and
SHA-256 verification steps.

## Capacity snapshot publication

Capacity and flow data is built from Azure DevOps revision history for each
area path. The first complete history backfill must finish successfully before
a capacity snapshot is published. Until then, the Capacity & Flow page has no
forecast to show for that area path.

A forecast is available only when at least three months contain completed
eligible work. Canceled items are excluded. If an item is reopened, it counts
only at its final completion.

## Usage

- Add an area path via the form on the home page (organization, project, area path, include sub-paths, active, interval in minutes).
- First sync for a new area path is a full load; subsequent syncs are incremental and remove items no longer in scope.
- Click "Sincronizar agora" to trigger a sync manually — disabled while a sync is already running for that area path.
- A red banner appears at the top if any area path's last sync failed due to an
  invalid/expired token — open the Synchronization page, update the Azure DevOps
  credential, and choose Save credential.
