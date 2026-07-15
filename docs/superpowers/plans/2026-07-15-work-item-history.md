# Work Item History Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync the full change history of every work item from Azure DevOps (via the Updates API) into a new `work_item_history` table, doing a one-time full backfill per area path and incremental delta updates thereafter.

**Architecture:** Extend the existing per-area-path sync pipeline (`ado_client.py` → `repository.py` → `sync_service.py`) with a parallel history-sync step. A new `get_work_item_updates` client method fetches paginated update records per work item; a new `upsert_work_item_history` repository function stores them idempotently keyed by `(work_item_id, rev)`; `sync_service._do_sync` decides whether to target all current work items (first history load) or just the delta, based on a new `area_paths.history_loaded_at` marker.

**Tech Stack:** Python, psycopg (raw SQL, no ORM), pytest, requests, Flask (unaffected by this change).

## Global Constraints

- Follows existing pattern: every repository function takes `conn` and does not commit; callers control transaction boundaries.
- Schema changes go in `app/db.py`'s `SCHEMA_SQL` as `CREATE TABLE IF NOT EXISTS` / appended `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — no separate migration files.
- All writes must be idempotent (re-running a sync must not duplicate or corrupt data), matching the existing upsert-by-primary-key pattern.
- Tests use the `db_conn` fixture from `tests/conftest.py`, which skips if `TEST_DATABASE_URL` is unset, and require truncating the new table between tests.
- API version stays `7.1`, consistent with `API_VERSION` in `app/ado_client.py`.

---

### Task 1: Schema — `work_item_history` table and `history_loaded_at` column

**Files:**
- Modify: `app/db.py` (append to `SCHEMA_SQL`)
- Test: `tests/test_db.py` (new file)

**Interfaces:**
- Produces: table `work_item_history(work_item_id INTEGER, area_path_id INTEGER, rev INTEGER, revised_by TEXT, revised_date TIMESTAMP, raw_json JSONB, synced_at TIMESTAMP, PRIMARY KEY (work_item_id, rev))` and column `area_paths.history_loaded_at TIMESTAMP`, both used by Task 3 (`repository.py`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_db.py`:

```python
from app import db


def test_init_schema_creates_work_item_history_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'work_item_history'
            ORDER BY column_name
            """
        )
        columns = {row[0]: row[1] for row in cur.fetchall()}

    assert columns["work_item_id"] == "integer"
    assert columns["area_path_id"] == "integer"
    assert columns["rev"] == "integer"
    assert columns["revised_by"] == "text"
    assert columns["revised_date"] == "timestamp without time zone"
    assert columns["raw_json"] == "jsonb"
    assert columns["synced_at"] == "timestamp without time zone"


def test_init_schema_adds_history_loaded_at_column(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'area_paths' AND column_name = 'history_loaded_at'
            """
        )
        row = cur.fetchone()

    assert row is not None
    assert row[0] == "timestamp without time zone"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — `work_item_history` table / `history_loaded_at` column do not exist (empty `columns` dict, or `row is None`).

- [ ] **Step 3: Write minimal implementation**

In `app/db.py`, modify `SCHEMA_SQL` (append after the existing `sync_logs` table and before the `ALTER TABLE area_paths ADD COLUMN IF NOT EXISTS last_error_msg TEXT;` line — order doesn't matter functionally, appending at the end is simplest):

```python
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS area_paths (
    id SERIAL PRIMARY KEY,
    organization TEXT NOT NULL,
    project TEXT NOT NULL,
    area_path TEXT NOT NULL,
    incluir_subpaths BOOLEAN NOT NULL DEFAULT TRUE,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    intervalo_minutos INTEGER NOT NULL DEFAULT 60,
    is_running BOOLEAN NOT NULL DEFAULT FALSE,
    last_sync_at TIMESTAMP,
    last_sync_status TEXT,
    last_sync_count INTEGER,
    last_error_msg TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS work_items (
    id INTEGER PRIMARY KEY,
    area_path_id INTEGER NOT NULL REFERENCES area_paths(id),
    title TEXT,
    work_item_type TEXT,
    state TEXT,
    assigned_to TEXT,
    changed_date TIMESTAMP,
    raw_json JSONB,
    synced_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sync_checkpoints (
    area_path_id INTEGER PRIMARY KEY REFERENCES area_paths(id),
    last_changed_date TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_logs (
    id SERIAL PRIMARY KEY,
    area_path_id INTEGER NOT NULL REFERENCES area_paths(id),
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    status TEXT,
    items_processed INTEGER,
    error_msg TEXT
);

CREATE TABLE IF NOT EXISTS work_item_history (
    work_item_id INTEGER NOT NULL,
    area_path_id INTEGER NOT NULL REFERENCES area_paths(id),
    rev INTEGER NOT NULL,
    revised_by TEXT,
    revised_date TIMESTAMP,
    raw_json JSONB,
    synced_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (work_item_id, rev)
);

ALTER TABLE area_paths ADD COLUMN IF NOT EXISTS last_error_msg TEXT;
ALTER TABLE area_paths ADD COLUMN IF NOT EXISTS history_loaded_at TIMESTAMP;
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Update `conftest.py`'s TRUNCATE list**

Modify `tests/conftest.py` line 21 so history tests start from a clean table each run:

```python
    with conn.cursor() as cur:
        cur.execute(
            "TRUNCATE sync_logs, sync_checkpoints, work_item_history, work_items, area_paths RESTART IDENTITY CASCADE"
        )
```

- [ ] **Step 6: Run full test suite to confirm nothing else broke**

Run: `pytest -v`
Expected: all PASS (existing tests unaffected; `test_db.py` new tests pass)

- [ ] **Step 7: Commit**

```bash
git add app/db.py tests/test_db.py tests/conftest.py
git commit -m "feat: add work_item_history table and history_loaded_at column"
```

---

### Task 2: `ado_client.py` — `get_work_item_updates` with pagination

**Files:**
- Modify: `app/ado_client.py`
- Test: `tests/test_ado_client.py`

**Interfaces:**
- Consumes: `self._auth()`, `AdoAuthError`, `AdoRetryExhaustedError`, `RETRY_DELAYS`, `API_VERSION` (all already defined in `app/ado_client.py`).
- Produces: `AdoClient.get_work_item_updates(self, work_item_id: int) -> list[dict]`, returning the raw `value` entries from the Updates API (each a dict with keys like `id`, `rev`, `revisedBy`, `revisedDate`, `fields`), used by Task 4 (`sync_service.py`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ado_client.py`:

```python
@patch("app.ado_client.requests.get")
def test_get_work_item_updates_single_page(mock_get):
    mock_get.return_value = _response(
        200,
        {
            "value": [
                {
                    "id": 1,
                    "rev": 2,
                    "revisedBy": {"uniqueName": "alice@example.com"},
                    "revisedDate": "2026-07-01T12:00:00Z",
                    "fields": {"System.State": {"oldValue": "New", "newValue": "Active"}},
                }
            ]
        },
    )

    client = AdoClient("org", "proj", pat="fake-pat")
    updates = client.get_work_item_updates(42)

    assert len(updates) == 1
    assert updates[0]["rev"] == 2
    sent_url = mock_get.call_args.args[0]
    assert "workitems/42/updates" in sent_url
    assert "api-version=7.1" in sent_url


@patch("app.ado_client.requests.get")
def test_get_work_item_updates_paginates_until_empty_page(mock_get):
    page1 = {"value": [{"id": 1, "rev": i} for i in range(100)]}
    page2 = {"value": [{"id": 1, "rev": 100}]}
    page3 = {"value": []}
    mock_get.side_effect = [_response(200, page1), _response(200, page2), _response(200, page3)]

    client = AdoClient("org", "proj", pat="fake-pat")
    updates = client.get_work_item_updates(42)

    assert len(updates) == 101
    assert mock_get.call_count == 3
    skips = [call.kwargs.get("params", {}).get("$skip") for call in mock_get.call_args_list]
    assert skips == [0, 100, 200]


@patch("app.ado_client.requests.get")
def test_get_work_item_updates_401_raises_auth_error(mock_get):
    mock_get.return_value = _response(401)

    client = AdoClient("org", "proj", pat="bad-pat")
    with pytest.raises(AdoAuthError):
        client.get_work_item_updates(42)


@patch("app.ado_client.time.sleep")
@patch("app.ado_client.requests.get")
def test_get_work_item_updates_retries_on_429(mock_get, mock_sleep):
    mock_get.side_effect = [
        _response(429),
        _response(200, {"value": []}),
    ]

    client = AdoClient("org", "proj", pat="fake-pat")
    updates = client.get_work_item_updates(42)

    assert updates == []
    mock_sleep.assert_called_once_with(5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ado_client.py -v -k get_work_item_updates`
Expected: FAIL with `AttributeError: 'AdoClient' object has no attribute 'get_work_item_updates'`

- [ ] **Step 3: Write minimal implementation**

In `app/ado_client.py`, add a `_get_with_retry` helper mirroring `_post_with_retry`, and `get_work_item_updates`:

```python
    def _get_with_retry(self, url: str, params: dict) -> dict:
        last_status = None
        for attempt in range(len(RETRY_DELAYS)):
            response = requests.get(url, params=params, auth=self._auth())

            if response.status_code == 401:
                raise AdoAuthError(f"Azure DevOps rejected credentials (401) calling {url}")

            if response.status_code in (429, 500, 502, 503, 504):
                last_status = response.status_code
                delay = RETRY_DELAYS[attempt]
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = max(delay, int(retry_after))
                    except ValueError:
                        pass
                time.sleep(delay)
                continue

            if response.status_code >= 400:
                try:
                    detail = response.json().get("message", response.text)
                except ValueError:
                    detail = response.text
                raise requests.HTTPError(
                    f"{response.status_code} error calling {url}: {detail}", response=response
                )
            return response.json()

        raise AdoRetryExhaustedError(
            f"Exhausted retries calling {url}, last status={last_status}"
        )

    def get_work_item_updates(self, work_item_id: int) -> list[dict]:
        url = (
            f"https://dev.azure.com/{self.organization}/{self.project}"
            f"/_apis/wit/workitems/{work_item_id}/updates"
        )
        page_size = 100
        results = []
        skip = 0
        while True:
            body = self._get_with_retry(url, {"api-version": API_VERSION, "$top": page_size, "$skip": skip})
            page = body.get("value", [])
            if not page:
                break
            results.extend(page)
            skip += page_size
        return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ado_client.py -v -k get_work_item_updates`
Expected: PASS

- [ ] **Step 5: Run full ado_client test file to confirm no regressions**

Run: `pytest tests/test_ado_client.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/ado_client.py tests/test_ado_client.py
git commit -m "feat: add get_work_item_updates with pagination to AdoClient"
```

---

### Task 3: `repository.py` — `upsert_work_item_history` and `set_history_loaded`

**Files:**
- Modify: `app/repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `work_item_history` table and `area_paths.history_loaded_at` column (Task 1).
- Produces:
  - `upsert_work_item_history(conn, area_path_id: int, work_item_id: int, updates: list[dict]) -> None` — each item in `updates` is a raw Updates-API entry dict (with `rev`, `revisedBy`, `revisedDate` keys as returned by `get_work_item_updates`).
  - `set_history_loaded(conn, area_path_id: int, when) -> None`
  - `get_history_loaded_at(conn, area_path_id: int)` — returns the stored `history_loaded_at` (datetime or `None`), used by Task 4.
  Used by Task 4 (`sync_service.py`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_repository.py`:

```python
def test_upsert_work_item_history_and_query(db_conn):
    area_path_id = _make_area_path(db_conn)
    updates = [
        {
            "rev": 1,
            "revisedBy": {"uniqueName": "alice@example.com"},
            "revisedDate": "2026-07-01T10:00:00Z",
            "fields": {"System.State": {"newValue": "New"}},
        },
        {
            "rev": 2,
            "revisedBy": {"uniqueName": "bob@example.com"},
            "revisedDate": "2026-07-02T10:00:00Z",
            "fields": {"System.State": {"oldValue": "New", "newValue": "Active"}},
        },
    ]

    repo.upsert_work_item_history(db_conn, area_path_id, 42, updates)
    db_conn.commit()

    with db_conn.cursor(row_factory=repo.dict_row) as cur:
        cur.execute(
            "SELECT * FROM work_item_history WHERE work_item_id = %s ORDER BY rev", (42,)
        )
        rows = cur.fetchall()

    assert len(rows) == 2
    assert rows[0]["rev"] == 1
    assert rows[0]["revised_by"] == "alice@example.com"
    assert rows[0]["revised_date"] == datetime.datetime(2026, 7, 1, 10, 0, 0)
    assert rows[0]["raw_json"]["fields"]["System.State"]["newValue"] == "New"
    assert rows[1]["revised_by"] == "bob@example.com"


def test_upsert_work_item_history_is_idempotent_by_rev(db_conn):
    area_path_id = _make_area_path(db_conn)
    update = {
        "rev": 1,
        "revisedBy": {"uniqueName": "alice@example.com"},
        "revisedDate": "2026-07-01T10:00:00Z",
        "fields": {"System.State": {"newValue": "New"}},
    }

    repo.upsert_work_item_history(db_conn, area_path_id, 42, [update])
    db_conn.commit()

    updated = dict(update, revisedBy={"uniqueName": "carol@example.com"})
    repo.upsert_work_item_history(db_conn, area_path_id, 42, [updated])
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM work_item_history WHERE work_item_id = 42")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT revised_by FROM work_item_history WHERE work_item_id = 42 AND rev = 1")
        assert cur.fetchone()[0] == "carol@example.com"


def test_upsert_work_item_history_empty_list_is_noop(db_conn):
    area_path_id = _make_area_path(db_conn)
    repo.upsert_work_item_history(db_conn, area_path_id, 42, [])
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM work_item_history")
        assert cur.fetchone()[0] == 0


def test_history_loaded_at_roundtrip(db_conn):
    area_path_id = _make_area_path(db_conn)
    assert repo.get_history_loaded_at(db_conn, area_path_id) is None

    when = datetime.datetime(2026, 7, 15, 11, 0, 0)
    repo.set_history_loaded(db_conn, area_path_id, when)
    db_conn.commit()

    assert repo.get_history_loaded_at(db_conn, area_path_id) == when
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_repository.py -v -k "history"`
Expected: FAIL with `AttributeError: module 'app.repository' has no attribute 'upsert_work_item_history'` (and similarly for the other new functions).

- [ ] **Step 3: Write minimal implementation**

Add to `app/repository.py` (needs `json` import at top of file — add `import json` alongside the existing `import psycopg`):

```python
import datetime
import json

import psycopg
from psycopg.rows import dict_row


def _parse_revised_date(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    return datetime.datetime.strptime(value.split(".")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S")


def upsert_work_item_history(
    conn: psycopg.Connection, area_path_id: int, work_item_id: int, updates: list[dict]
) -> None:
    if not updates:
        return
    with conn.cursor() as cur:
        for update in updates:
            revised_by_field = update.get("revisedBy")
            revised_by = (
                revised_by_field.get("uniqueName")
                if isinstance(revised_by_field, dict)
                else revised_by_field
            )
            cur.execute(
                """
                INSERT INTO work_item_history
                    (work_item_id, area_path_id, rev, revised_by, revised_date, raw_json, synced_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (work_item_id, rev) DO UPDATE SET
                    area_path_id = EXCLUDED.area_path_id,
                    revised_by = EXCLUDED.revised_by,
                    revised_date = EXCLUDED.revised_date,
                    raw_json = EXCLUDED.raw_json,
                    synced_at = now()
                """,
                (
                    work_item_id,
                    area_path_id,
                    update["rev"],
                    revised_by,
                    _parse_revised_date(update.get("revisedDate")),
                    json.dumps(update),
                ),
            )


def set_history_loaded(conn: psycopg.Connection, area_path_id: int, when) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE area_paths SET history_loaded_at = %s WHERE id = %s", (when, area_path_id)
        )


def get_history_loaded_at(conn: psycopg.Connection, area_path_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT history_loaded_at FROM area_paths WHERE id = %s", (area_path_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None
```

Note: `dict_row`-based test reads `raw_json` back as a parsed dict automatically (psycopg's `jsonb` adapter deserializes it), so `rows[0]["raw_json"]["fields"]...` in the test works directly against the stored `json.dumps(update)` string.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_repository.py -v -k "history"`
Expected: PASS

- [ ] **Step 5: Run full repository test file to confirm no regressions**

Run: `pytest tests/test_repository.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/repository.py tests/test_repository.py
git commit -m "feat: add work item history upsert and history_loaded_at tracking to repository"
```

---

### Task 4: `sync_service.py` — wire history sync into `_do_sync`

**Files:**
- Modify: `app/sync_service.py`
- Test: `tests/test_sync_service.py`

**Interfaces:**
- Consumes:
  - `client.get_work_item_updates(work_item_id: int) -> list[dict]` (Task 2)
  - `repo.upsert_work_item_history(conn, area_path_id, work_item_id, updates)` (Task 3)
  - `repo.get_history_loaded_at(conn, area_path_id)` (Task 3)
  - `repo.set_history_loaded(conn, area_path_id, when)` (Task 3)
- Produces: no new public functions — `_do_sync` behavior changes only. `run_sync`'s return shape (`{"status": ..., "items_processed": ...}`) is unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sync_service.py`:

```python
def test_first_sync_backfills_history_for_all_current_ids_and_marks_loaded(db_conn):
    row = _area_path_row(db_conn)
    client = MagicMock()
    client.get_all_ids.return_value = [1, 2]
    client.get_changed_ids.return_value = [1]  # only item 1 changed
    client.get_work_items_batch.return_value = [
        {
            "id": 1,
            "title": "A",
            "work_item_type": "Bug",
            "state": "Active",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 1),
            "raw_json": "{}",
        }
    ]
    client.get_work_item_updates.return_value = [
        {"rev": 1, "revisedBy": {"uniqueName": "alice@example.com"}, "revisedDate": "2026-07-01T10:00:00Z", "fields": {}}
    ]

    result = sync_service.run_sync(db_conn, row, client)
    db_conn.commit()

    assert result["status"] == "ok"
    # first sync: history fetched for every current id (1 and 2), not just the changed one
    called_ids = sorted(call.args[0] for call in client.get_work_item_updates.call_args_list)
    assert called_ids == [1, 2]
    assert repo.get_history_loaded_at(db_conn, row["id"]) is not None
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM work_item_history WHERE work_item_id IN (1, 2)")
        assert cur.fetchone()[0] == 2


def test_subsequent_sync_only_fetches_history_for_delta(db_conn):
    row = _area_path_row(db_conn)
    repo.set_history_loaded(db_conn, row["id"], datetime.datetime(2026, 7, 10))
    db_conn.commit()
    row = repo.get_area_path(db_conn, row["id"])

    client = MagicMock()
    client.get_all_ids.return_value = [1, 2]
    client.get_changed_ids.return_value = [2]  # only item 2 changed this cycle
    client.get_work_items_batch.return_value = [
        {
            "id": 2,
            "title": "B",
            "work_item_type": "Task",
            "state": "New",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 15),
            "raw_json": "{}",
        }
    ]
    client.get_work_item_updates.return_value = []

    result = sync_service.run_sync(db_conn, row, client)
    db_conn.commit()

    assert result["status"] == "ok"
    called_ids = [call.args[0] for call in client.get_work_item_updates.call_args_list]
    assert called_ids == [2]


def test_history_sync_failure_leaves_history_loaded_at_unset(db_conn):
    row = _area_path_row(db_conn)
    client = MagicMock()
    client.get_all_ids.return_value = [1]
    client.get_changed_ids.return_value = [1]
    client.get_work_items_batch.return_value = [
        {
            "id": 1,
            "title": "A",
            "work_item_type": "Bug",
            "state": "Active",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 1),
            "raw_json": "{}",
        }
    ]
    client.get_work_item_updates.side_effect = AdoRetryExhaustedError("gave up")

    result = sync_service.run_sync(db_conn, row, client)
    db_conn.commit()

    assert result["status"] == "error"
    assert repo.get_history_loaded_at(db_conn, row["id"]) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sync_service.py -v -k "history"`
Expected: FAIL — `client.get_work_item_updates` never called (assertions on `called_ids` fail with empty lists), and `get_history_loaded_at` stays `None` in the first test.

- [ ] **Step 3: Write minimal implementation**

Modify `_do_sync` in `app/sync_service.py`:

```python
def _do_sync(conn, area_path_row: dict, client: AdoClient) -> int:
    area_path_id = area_path_row["id"]
    area_path = area_path_row["area_path"]
    incluir_subpaths = area_path_row["incluir_subpaths"]

    current_ids = set(client.get_all_ids(area_path, incluir_subpaths))

    checkpoint = repo.get_checkpoint(conn, area_path_id)
    changed_ids = client.get_changed_ids(area_path, incluir_subpaths, since=checkpoint)

    items = client.get_work_items_batch(changed_ids)
    repo.upsert_work_items(conn, area_path_id, items)

    stored_ids = repo.get_work_item_ids(conn, area_path_id)
    removed_ids = stored_ids - current_ids
    repo.delete_work_items(conn, area_path_id, removed_ids)

    if items:
        max_changed_date = max(item["changed_date"] for item in items if item["changed_date"])
        repo.set_checkpoint(conn, area_path_id, max_changed_date)

    is_first_history_load = repo.get_history_loaded_at(conn, area_path_id) is None
    history_target_ids = current_ids if is_first_history_load else set(changed_ids)
    for work_item_id in history_target_ids:
        updates = client.get_work_item_updates(work_item_id)
        repo.upsert_work_item_history(conn, area_path_id, work_item_id, updates)
    if is_first_history_load:
        repo.set_history_loaded(conn, area_path_id, datetime.datetime.now())

    return len(items)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sync_service.py -v -k "history"`
Expected: PASS

- [ ] **Step 5: Run full test suite to confirm no regressions**

Run: `pytest -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/sync_service.py tests/test_sync_service.py
git commit -m "feat: sync work item history per area path, full backfill then delta"
```

---

## Self-Review Notes

- **Spec coverage:** Schema (Task 1) ✓, Updates API client + pagination (Task 2) ✓, repository upsert + `history_loaded_at` marker (Task 3) ✓, sync_service wiring for first-load-vs-delta + error propagation (Task 4) ✓. Out-of-scope items (UI, field normalization) correctly have no task.
- **Placeholder scan:** none found — every step has concrete code.
- **Type consistency:** `get_work_item_updates(work_item_id: int) -> list[dict]` (Task 2) matches its usage in Task 4 (`client.get_work_item_updates(work_item_id)`). `upsert_work_item_history(conn, area_path_id, work_item_id, updates)` signature matches across Task 3 definition and Task 4 call site. `get_history_loaded_at` / `set_history_loaded` names match between Task 3 and Task 4.
