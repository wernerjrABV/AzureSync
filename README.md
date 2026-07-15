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

```bash
cd apps/sync-service
pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:5000. See `apps/sync-service/README.md` for env vars
and test setup.

## Roadmap

Today: `apps/sync-service` is the only app, and the only database writer.

Next:
1. `apps/api-read` — read-only backend querying the same database.
2. `apps/web-read` — frontend listing data via `apps/api-read`.
3. Database index review for the new read-heavy access pattern.

Each of the above will land as its own design spec + implementation plan
(see `docs/superpowers/specs/` and `docs/superpowers/plans/`) — this repo is
built incrementally, not as a big-bang rewrite.

## Governance

- Architecture decisions: `docs/adr/`
- Technology lifecycle (semestral review, V-2 annual upgrade rule):
  `docs/standards/technology-lifecycle.md`
- Single-writer rule: `docs/adr/0002-single-writer.md`
