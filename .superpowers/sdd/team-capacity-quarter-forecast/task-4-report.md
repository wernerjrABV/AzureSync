# Task 4 report — read-only capacity API

## Delivered

- Added the SELECT-only `get_capacity_snapshot` repository query, scoped by
  `area_path_id`.
- Added `GET /api/capacity`, validating `area_path_id`, four-digit `year`, and
  `quarter` 1 through 4.
- Returns `{ "data": null }` when no snapshot exists; otherwise returns the
  stored payload with `selected_period`.
- Added the SQLite fallback `capacity_snapshots` schema and JSON-text payload
  parsing while retaining PostgreSQL dict-row behavior.

## TDD evidence

- Repository tests initially failed because the query and SQLite schema did not
  exist; after implementation, the focused repository suite passed.
- Route tests initially failed with 404 because the endpoint did not exist;
  after implementation, all focused route tests passed.

## Verification

Executed from `apps/api-read` with
`TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/azure_sync_test`:

```text
C:\Projects\AzureSync\apps\api-read\.venv\Scripts\python.exe -m pytest tests/test_repository.py tests/test_routes.py tests/test_readonly_guardrail.py -v
56 passed in 11.02s
```

The read-only guardrail passed. No write SQL was added to `apps/api-read`.

## Round 1 review fix

- Tightened `/api/capacity` year validation to require four ASCII decimal
  digits before opening the read connection or converting the value with
  `int()`.
- Added a regression test with the Unicode superscript-digit year `²²²²` and
  a stored snapshot. Before the fix it reproduced the reviewer finding as a
  `ValueError` during `int(year_text)`; it now returns HTTP 400.

Verification rerun with the same focused API command:

```text
57 passed in 10.71s
```

The regression test was also run against the original `isdigit()` guard and
failed with `ValueError` at `int(year_text)`, confirming the reported failure
mode before the ASCII-safe guard was restored.
