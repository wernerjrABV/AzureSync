# Azure DevOps Sync Monorepo

Enterprise monorepo for syncing Azure DevOps work items into PostgreSQL and
(in future phases) exposing them for read-only consumption.

## Layout

```
apps/
  sync-service/      Flask app — syncs Azure DevOps → PostgreSQL.
                      The ONLY app in this repo authorized to write to
                      the database. See apps/sync-service/README.md.
packages/
  shared-contracts/       (placeholder) DTOs/schemas shared across apps.
  shared-config/          (placeholder) lint/formatter/convention templates.
  shared-observability/   (placeholder) logging/tracing/metrics helpers.
  shared-db-guidelines/   (placeholder) data-access documentation/utilities.
docs/
  architecture/       System-level architecture docs.
  adr/                Architecture Decision Records.
  standards/          Technology lifecycle / governance rules.
```

## Running the sync service

### Starting all apps on Windows

To start the sync service, read API, and web frontend at once, double-click
`scripts/run-all.cmd`. It runs the services without leaving a terminal window
open and launches the web interface at http://127.0.0.1:5173.

To stop the services later, run `scripts/stop-all.ps1` from PowerShell.
Runtime logs are written to the local `logs/` directory.

```bash
cd apps/sync-service
pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:5000. See `apps/sync-service/README.md` for env vars
and test setup.

## Running the read path

The read path consists of two apps: `apps/api-read` (read-only backend) and
`apps/web-read` (React frontend).

**Via PowerShell (Windows):**

```powershell
# Terminal 1: Start the read API
.\scripts\run-api-read.ps1

# Terminal 2: Start the web frontend
.\scripts\run-web-read.ps1
```

Open http://127.0.0.1:5173 (web-read default port). See `apps/api-read/README.md`
and `apps/web-read/README.md` for env vars and configuration. Full architecture
at `docs/architecture/read-path-architecture.md`.

## Roadmap

**Complete:**
- `apps/sync-service` — the only database writer (syncs Azure DevOps to PostgreSQL).
- `apps/api-read` — read-only backend querying the same database.
- `apps/web-read` — frontend listing data via `apps/api-read`.
- Database index review for the read-heavy access pattern.

**Next:**

Each phase lands as its own design spec + implementation plan
(see `docs/superpowers/specs/` and `docs/superpowers/plans/`) — this repo is
built incrementally, not as a big-bang rewrite.

## Governance

- Architecture decisions: `docs/adr/`
- Technology lifecycle (semestral review, V-2 annual upgrade rule):
  `docs/standards/technology-lifecycle.md`
- Single-writer rule: `docs/adr/0002-single-writer.md`
