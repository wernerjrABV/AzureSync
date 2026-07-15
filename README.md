# Azure DevOps → PostgreSQL Sync

Local app that syncs Azure DevOps work items (by area path) into an existing local PostgreSQL database.

## Setup

1. Set Windows environment variables:
   - `DATABASE_URL` — e.g. `postgresql://user:pass@localhost:5432/azure_sync`
   - `AZURE_DEVOPS_API_KEY` — your Azure DevOps Personal Access Token
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run:
   ```
   python run.py
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
