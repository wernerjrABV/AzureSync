## Task 1 report — application-settings schema and repository boundary

### Scope completed

- Added `app_settings(key, encrypted_value, updated_at)` to both PostgreSQL and SQLite schema definitions in `apps/sync-service/app/db.py`.
- Added repository boundary functions in `apps/sync-service/app/repository.py`:
  - `get_app_setting(conn, key)`
  - `upsert_app_setting(conn, *, key, encrypted_value, updated_at)`
  - `delete_app_setting(conn, key)`
- Tightened the storage boundary so only `azure_devops_api_key` is accepted and
  `encrypted_value` must be 4096 characters or fewer; invalid input now raises
  `ValueError` from `repository.py`.
- Extended PostgreSQL test cleanup in `apps/sync-service/tests/conftest.py` to
  truncate `app_settings`, so app-setting tests do not leak data between cases.
- Added tests in:
  - `apps/sync-service/tests/test_sqlite_fallback.py`
  - `apps/sync-service/tests/test_repository.py`
  - `apps/sync-service/tests/test_db.py`
  - `apps/sync-service/tests/conftest.py` (cleanup coverage path)

### TDD evidence

#### RED

Command:

```powershell
pytest tests/test_sqlite_fallback.py -k app_setting -v
```

Result:

- `tests/test_sqlite_fallback.py::test_sqlite_schema_persists_replaces_and_deletes_app_setting`
  failed with:
  - `AttributeError: module 'app.repository' has no attribute 'upsert_app_setting'`

Command:

```powershell
pytest tests/test_db.py -k app_settings -v
pytest tests/test_repository.py -k app_setting -v
```

Result:

- Both PostgreSQL-backed checks were skipped under the repository’s existing
  `TEST_DATABASE_URL` gate in this environment, which matches the task brief’s
  allowed outcome when no configured test database is present.

#### GREEN

Command:

```powershell
pytest tests/test_sqlite_fallback.py tests/test_repository.py -v
```

Result:

- `4 passed, 22 skipped`
- New SQLite app-settings persistence test passed.
- PostgreSQL repository tests remained skipped because `TEST_DATABASE_URL` is not configured.

Command:

```powershell
pytest tests/test_db.py -v
```

Result:

- `7 skipped`
- PostgreSQL schema checks, including the new `app_settings` assertion, remained
  skipped because `TEST_DATABASE_URL` is not configured.

### Notes from self-review

- The change stays within the repository boundary: all write SQL for app settings
  is in `repository.py`.
- The explicit `updated_at` argument keeps SQLite and PostgreSQL behavior aligned.
- The invariant enforcement is centralized in repository validation so both
  SQLite and PostgreSQL callers see the same behavior and error messages.
- No unrelated sync or Azure DevOps behavior was touched.

### Concerns

- I could not execute the PostgreSQL branch of the new repository/schema tests in
  this environment because `TEST_DATABASE_URL` is not set, so PostgreSQL coverage
  is limited to the test definitions rather than a live run here.

## Reviewer follow-up fixes

### Reviewer issue 1: PostgreSQL cleanup omitted `app_settings`

Change:

- Updated the `db_conn` fixture cleanup SQL in `tests/conftest.py` to include
  `app_settings` in the `TRUNCATE ... RESTART IDENTITY CASCADE` list.

Coverage:

- Added PostgreSQL fixture-isolation tests in `tests/test_repository.py`:
  - `test_app_setting_cleanup_seed`
  - `test_app_setting_cleanup_isolates_between_tests`

Environment result:

- These tests remain skipped here because `TEST_DATABASE_URL` is not configured,
  but they now exercise the intended isolation path when a PostgreSQL test
  database is available.

### Reviewer issue 2: storage boundary did not enforce credential invariants

Added failing tests first:

```powershell
pytest tests/test_sqlite_fallback.py -k 'app_setting and not persists' -v
```

RED result:

- `test_sqlite_app_setting_rejects_unknown_key` failed with
  `Failed: DID NOT RAISE <class 'ValueError'>`
- `test_sqlite_app_setting_rejects_values_longer_than_4096` failed with
  `Failed: DID NOT RAISE <class 'ValueError'>`

Implementation:

- Added repository validation for:
  - allowed key exactly `azure_devops_api_key`
  - `encrypted_value` maximum length 4096
- Invalid values now raise:
  - `ValueError("app setting key must be 'azure_devops_api_key'")`
  - `ValueError("app setting encrypted_value must be at most 4096 characters")`

Added/updated tests:

- SQLite runnable coverage:
  - `test_sqlite_app_setting_rejects_unknown_key`
  - `test_sqlite_app_setting_rejects_values_longer_than_4096`
- PostgreSQL gated coverage:
  - `test_app_setting_rejects_unknown_key`
  - `test_app_setting_rejects_values_longer_than_4096`

GREEN result:

```powershell
pytest tests/test_sqlite_fallback.py -k app_setting -v
pytest tests/test_repository.py -k app_setting -v
```

- SQLite: `3 passed, 3 deselected`
- PostgreSQL-gated repository tests: `5 skipped, 21 deselected`

### Reviewer issue 3: storage boundary accepted arbitrary short strings

Problem:

- The repository validation still accepted arbitrary short strings such as
  `"cipher-one"` as `encrypted_value`, which is too weak for the intended DPAPI
  ciphertext boundary.

Test-first changes:

- Updated the positive app-setting tests to use valid standard Base64 payloads:
  - `Y2lwaGVyLW9uZQ==`
  - `Y2lwaGVyLXR3bw==`
- Added new SQLite and PostgreSQL-gated repository tests for:
  - empty ciphertext rejection
  - non-Base64 ciphertext rejection

RED command:

```powershell
pytest tests/test_sqlite_fallback.py -k 'app_setting and (empty or non_base64 or persists)' -v
```

RED result:

- `test_sqlite_schema_persists_replaces_and_deletes_app_setting` passed with valid Base64 fixtures
- `test_sqlite_app_setting_rejects_empty_ciphertext` failed with
  `Failed: DID NOT RAISE <class 'ValueError'>`
- `test_sqlite_app_setting_rejects_non_base64_ciphertext` failed with
  `Failed: DID NOT RAISE <class 'ValueError'>`

Implementation:

- Added strict Base64 validation in `repository.py` using
  `base64.b64decode(..., validate=True)`.
- Required `encrypted_value` to be:
  - non-empty
  - valid standard Base64
  - canonical when re-encoded to Base64

Error surfaced:

- Invalid ciphertext now raises:
  - `ValueError("app setting encrypted_value must be non-empty Base64")`

Added/updated tests:

- SQLite runnable coverage:
  - `test_sqlite_schema_persists_replaces_and_deletes_app_setting`
  - `test_sqlite_app_setting_rejects_empty_ciphertext`
  - `test_sqlite_app_setting_rejects_non_base64_ciphertext`
- PostgreSQL gated coverage:
  - `test_app_setting_roundtrip_replaces_existing_value`
  - `test_app_setting_rejects_empty_ciphertext`
  - `test_app_setting_rejects_non_base64_ciphertext`

GREEN result:

```powershell
pytest tests/test_sqlite_fallback.py -k app_setting -v
pytest tests/test_repository.py -k app_setting -v
```

- SQLite: `5 passed, 3 deselected`
- PostgreSQL-gated repository tests: `7 skipped, 21 deselected`
