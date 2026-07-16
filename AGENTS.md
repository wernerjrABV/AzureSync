# AGENTS.md

Codex guidance for this repo. Keep `docs/architecture/monorepo-architecture.md` in mind for the full picture.

## UI / Frontend Rule

- Sempre use exclusivamente o design system Astryx e seus componentes.
- Nunca crie ou introduza CSS estilizado manualmente, incluindo `styled-components`, `emotion`, CSS inline ou folhas de estilo customizadas quando houver alternativa no Astryx.
- Se um padrão visual ainda não existir no Astryx, prefira compor a interface com componentes existentes do sistema em vez de criar estilo ad hoc.

## Non-Negotiables

- `apps/sync-service/` is the only database writer.
- `repository.py` is the only file that issues write SQL.
- `create_app(conn_factory=...)` is the supported test hook for request-scoped DB access.
- `sync_service.run_sync` owns locking, checkpoint advancement, upserts, deletes, and history backfill.
- `history_loaded_at` only flips after a full first-load history backfill completes with zero item failures.
- On sync failure, roll back before writing error status.

## Workflow

- Prefer small, isolated edits over broad refactors.
- Preserve existing patterns unless a change is required by the task.
- Add or update tests when changing sync behavior, schema behavior, or route behavior.
- If a change touches write paths, check `repository.py`, `sync_service.py`, and the relevant tests together.

## `apps/sync-service` Commands

```bash
cd apps/sync-service

pip install -r requirements.txt
python run.py

createdb azure_sync_test
set TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/azure_sync_test
pytest

pytest tests/test_sync_service.py
pytest tests/test_sync_service.py::test_name -v
```

## Environment

- `DATABASE_URL` - app database connection string.
- `TEST_DATABASE_URL` - separate Postgres DB for tests; if unset, tests are skipped.
- `AZURE_DEVOPS_API_KEY` - Azure DevOps PAT for `AdoClient`.

Windows env vars only. No `.env` file.

## Architecture Notes

- Sync scope is per `area_path`.
- `ado_client.py` uses WIQL + work item batch REST calls.
- `get_changed_ids` uses date precision, not datetime, in the `ChangedDate` filter.
- Deletions are based on current ADO IDs versus stored IDs.
- `scheduler.py` computes per-area due time in Python, not separate jobs.
- `db.py` keeps schema in `SCHEMA_SQL` plus appended `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
- `repository.py` must remain transaction-boundary agnostic; callers control commits and rollbacks.
- `sync_service.run_sync` should remain idempotent across retries and partial failures.

## Schema

- `area_paths` -> `work_items`, `sync_checkpoints`, `sync_logs`.
- `work_item_history` is keyed by `(work_item_id, rev)` and is not FK'd to `work_items`.
- `raw_json` stores the full ADO payload.
- `area_paths.history_loaded_at` marks completion of the one-time history backfill.

## Failure Surfacing

- Sync failures are stored in row fields (`last_sync_status`, `last_error_msg`).
- `routes.py` flags `auth_error` so the UI can prompt for `AZURE_DEVOPS_API_KEY`.

## Planned Apps

- `apps/api-read/` - read-only backend.
- `apps/web-read/` - frontend that consumes `apps/api-read`.
