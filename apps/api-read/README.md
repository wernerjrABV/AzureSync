# api-read

Read-only Flask API over the Postgres database populated by
`apps/sync-service`. **This service must never write to the database.**
`apps/sync-service` is the only writer (see
`docs/adr/0002-single-writer.md` and `docs/adr/0003-read-only-api.md`).

## Architectural limits

- No INSERT/UPDATE/DELETE/UPSERT SQL anywhere in `app/` — enforced by
  `tests/test_readonly_guardrail.py`.
- No schema/DDL statements — schema is owned entirely by
  `apps/sync-service/app/db.py`.
- Uses the same `DATABASE_URL` as sync-service today; there is no separate
  read-only DB role yet (tracked as a known gap in
  `docs/adr/0003-read-only-api.md`).

## Running

```bash
cd apps/api-read
pip install -r requirements.txt
set DATABASE_URL=postgresql://postgres:postgres@localhost:5432/azure_sync
python run.py
```

Server starts on `http://127.0.0.1:5001` by default (override with
`API_READ_HOST` / `API_READ_PORT`).

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | yes | — | Postgres connection string (same DB as sync-service) |
| `API_READ_HOST` | no | `127.0.0.1` | Bind host |
| `API_READ_PORT` | no | `5001` | Bind port |
| `API_READ_CORS_ORIGIN` | no | `http://127.0.0.1:5173,http://localhost:5173` | Comma-separated list of origins allowed via `Access-Control-Allow-Origin` (should include whatever origin `apps/web-read`'s dev server is actually opened from — `localhost` and `127.0.0.1` are treated as different origins by browsers) |
| `TEST_DATABASE_URL` | no (tests only) | — | Separate Postgres DB for tests; tests are skipped if unset |

## Endpoints

- `GET /health` — liveness check.
- `GET /api/area-paths` — list of area paths.
- `GET /api/work-items?area_path_id=&work_item_type=&page=&page_size=&order_by=&order_dir=` —
  paginated work item listing. See
  `packages/shared-contracts/work-item-listing.md` for the full contract.

## Tests

```bash
createdb azure_sync_test
set TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/azure_sync_test
cd apps/sync-service && python -c "from app import db; c = db.get_connection(); db.init_schema(c); c.commit()"
cd ../api-read
pytest
```

Note: api-read's tests assume the schema already exists in
`TEST_DATABASE_URL` — run sync-service's schema init once against that DB
first (as shown above), since api-read itself never runs DDL.
