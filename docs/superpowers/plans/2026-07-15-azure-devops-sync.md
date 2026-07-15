# Azure DevOps → PostgreSQL Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Local Windows app that syncs Azure DevOps work items (by area path, with optional sub-paths) into an existing local PostgreSQL database — full load on first run, incremental delta (including deletions) afterward — with a simple Flask CRUD UI and a manual "sync now" button.

**Architecture:** A Flask app (server-rendered Jinja2) provides CRUD over `area_paths` and a manual sync trigger. An in-process APScheduler runs the same sync function on each area path's configured interval. The sync function talks to Azure DevOps via a thin REST client (WIQL for id lists, `workitemsbatch` for field data), diffs current vs. stored ids to upsert changes and hard-delete removed/moved items, and persists a checkpoint (`last_changed_date`) plus a `sync_logs` row per run. A DB-backed boolean lock (`area_paths.is_running`) prevents manual and scheduled runs from overlapping.

**Tech Stack:** Python 3.12, Flask, psycopg (v3, no ORM), APScheduler, `requests`, PostgreSQL (existing local instance).

## Global Constraints

- No Docker, no microservices, no Redis, no queues, no websocket, no user auth, no sophisticated UI (spec section "Fora de escopo").
- Credential comes only from the Windows environment variable `AZURE_DEVOPS_API_KEY` — never stored in DB or config file.
- Retry policy for 429/5xx is fixed delays **5s → 15s → 30s** (3 attempts), not a computed exponential backoff.
- 401 responses must NOT be retried — they set `auth_error` immediately.
- Item deletion in Azure DevOps must result in physical `DELETE` from `work_items` (no soft-delete/history — spec explicitly excludes this).
- `incluir_subpaths` must change the WIQL operator: `UNDER` when true, `=` when false.
- `is_running` is the only concurrency guard; it must be set/cleared atomically via a conditional `UPDATE ... WHERE is_running = FALSE`.

---

## File Structure

```
azureDataQuery/
  app/
    __init__.py
    config.py            # env var reads (DATABASE_URL, AZURE_DEVOPS_API_KEY)
    db.py                # connection + schema init
    repository.py        # all SQL (area_paths, work_items, checkpoints, sync_logs)
    ado_client.py         # Azure DevOps REST client + retry + exceptions
    sync_service.py       # full/delta sync orchestration, lock, logging
    scheduler.py          # APScheduler wiring
    routes.py             # Flask blueprint: list/create/edit/delete/sync
    templates/
      index.html
      area_path_form.html
  tests/
    conftest.py
    test_db.py
    test_repository.py
    test_ado_client.py
    test_sync_service.py
    test_routes.py
  run.py                  # entrypoint: create app, start scheduler, app.run()
  requirements.txt
  README.md
```

---

### Task 1: Project scaffold, config, DB connection + schema

**Files:**
- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/db.py`
- Create: `tests/conftest.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - `app.config.DATABASE_URL: str`, `app.config.AZURE_DEVOPS_API_KEY: str` (read lazily via functions, not module-level constants, so tests can monkeypatch env vars)
  - `app.config.get_database_url() -> str`
  - `app.config.get_ado_api_key() -> str`
  - `app.db.get_connection() -> psycopg.Connection` (autocommit=False, caller manages transaction)
  - `app.db.init_schema(conn) -> None`
  - `tests/conftest.py` fixture `db_conn` — connects to `TEST_DATABASE_URL`, runs `init_schema`, truncates all tables before each test, yields the connection, rolls back+closes after.

This task requires a local Postgres reachable via the `TEST_DATABASE_URL` env var (e.g. `postgresql://postgres:postgres@localhost:5432/azure_sync_test`). Create that database manually before running tests:
```
createdb azure_sync_test
```

- [ ] **Step 1: Write requirements.txt**

```
flask==3.1.0
psycopg[binary]==3.2.3
apscheduler==3.10.4
requests==2.32.3
pytest==8.3.3
```

- [ ] **Step 2: Create app package init**

`app/__init__.py`:
```python
```
(empty — package marker only)

- [ ] **Step 3: Write config.py**

`app/config.py`:
```python
import os


def get_database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return value


def get_ado_api_key() -> str:
    value = os.environ.get("AZURE_DEVOPS_API_KEY")
    if not value:
        raise RuntimeError("AZURE_DEVOPS_API_KEY environment variable is not set")
    return value
```

- [ ] **Step 4: Write the failing test for schema init**

`tests/test_db.py`:
```python
from app import db


def test_init_schema_creates_all_tables(db_conn):
    db.init_schema(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        )
        tables = {row[0] for row in cur.fetchall()}

    assert {"area_paths", "work_items", "sync_checkpoints", "sync_logs"} <= tables
```

- [ ] **Step 5: Write conftest.py (needed for the test above to run)**

`tests/conftest.py`:
```python
import os

import psycopg
import pytest

from app import db


@pytest.fixture
def db_conn():
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL not set")

    conn = psycopg.connect(dsn)
    db.init_schema(conn)
    conn.commit()

    with conn.cursor() as cur:
        cur.execute(
            "TRUNCATE sync_logs, sync_checkpoints, work_items, area_paths RESTART IDENTITY CASCADE"
        )
    conn.commit()

    yield conn

    conn.rollback()
    conn.close()
```

- [ ] **Step 6: Run test to verify it fails (db.py doesn't exist yet)**

Run: `set TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/azure_sync_test && pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError: cannot import name 'db'`

- [ ] **Step 7: Write db.py**

`app/db.py`:
```python
import psycopg

from app.config import get_database_url

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
"""


def get_connection() -> psycopg.Connection:
    return psycopg.connect(get_database_url())


def init_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add requirements.txt app/__init__.py app/config.py app/db.py tests/conftest.py tests/test_db.py
git commit -m "feat: add config, db connection, and schema init"
```

---

### Task 2: Area path repository (CRUD + lock)

**Files:**
- Create: `app/repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `app.db.get_connection`, `app.db.init_schema` (Task 1)
- Produces:
  - `create_area_path(conn, organization, project, area_path, incluir_subpaths=True, ativo=True, intervalo_minutos=60) -> int`
  - `list_area_paths(conn) -> list[dict]`
  - `get_area_path(conn, area_path_id) -> dict | None`
  - `update_area_path(conn, area_path_id, **fields) -> None`
  - `delete_area_path(conn, area_path_id) -> None`
  - `try_acquire_lock(conn, area_path_id) -> bool` (True if lock acquired)
  - `release_lock(conn, area_path_id) -> None`
  - `update_sync_result(conn, area_path_id, status, count, synced_at) -> None`

Every dict returned has keys matching the `area_paths` columns exactly (e.g. `id`, `organization`, `project`, `area_path`, `incluir_subpaths`, `ativo`, `intervalo_minutos`, `is_running`, `last_sync_at`, `last_sync_status`, `last_sync_count`, `created_at`).

- [ ] **Step 1: Write the failing tests**

`tests/test_repository.py`:
```python
from app import repository as repo


def test_create_and_get_area_path(db_conn):
    area_path_id = repo.create_area_path(
        db_conn, "myorg", "myproj", "myproj\\Team A", incluir_subpaths=False, intervalo_minutos=30
    )
    db_conn.commit()

    row = repo.get_area_path(db_conn, area_path_id)

    assert row["organization"] == "myorg"
    assert row["project"] == "myproj"
    assert row["area_path"] == "myproj\\Team A"
    assert row["incluir_subpaths"] is False
    assert row["ativo"] is True
    assert row["intervalo_minutos"] == 30
    assert row["is_running"] is False


def test_list_area_paths_returns_all(db_conn):
    repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    repo.create_area_path(db_conn, "org", "proj", "proj\\B")
    db_conn.commit()

    rows = repo.list_area_paths(db_conn)

    assert len(rows) == 2


def test_update_area_path(db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()

    repo.update_area_path(db_conn, area_path_id, ativo=False, intervalo_minutos=15)
    db_conn.commit()

    row = repo.get_area_path(db_conn, area_path_id)
    assert row["ativo"] is False
    assert row["intervalo_minutos"] == 15


def test_delete_area_path(db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()

    repo.delete_area_path(db_conn, area_path_id)
    db_conn.commit()

    assert repo.get_area_path(db_conn, area_path_id) is None


def test_acquire_lock_succeeds_when_free(db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()

    acquired = repo.try_acquire_lock(db_conn, area_path_id)
    db_conn.commit()

    assert acquired is True
    assert repo.get_area_path(db_conn, area_path_id)["is_running"] is True


def test_acquire_lock_fails_when_already_running(db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()
    repo.try_acquire_lock(db_conn, area_path_id)
    db_conn.commit()

    acquired_again = repo.try_acquire_lock(db_conn, area_path_id)
    db_conn.commit()

    assert acquired_again is False


def test_release_lock(db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()
    repo.try_acquire_lock(db_conn, area_path_id)
    db_conn.commit()

    repo.release_lock(db_conn, area_path_id)
    db_conn.commit()

    assert repo.get_area_path(db_conn, area_path_id)["is_running"] is False


def test_update_sync_result(db_conn):
    import datetime

    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()

    now = datetime.datetime(2026, 7, 15, 10, 0, 0)
    repo.update_sync_result(db_conn, area_path_id, status="ok", count=42, synced_at=now)
    db_conn.commit()

    row = repo.get_area_path(db_conn, area_path_id)
    assert row["last_sync_status"] == "ok"
    assert row["last_sync_count"] == 42
    assert row["last_sync_at"] == now
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.repository'`

- [ ] **Step 3: Write repository.py (area_paths portion)**

`app/repository.py`:
```python
import psycopg
from psycopg.rows import dict_row


def create_area_path(
    conn: psycopg.Connection,
    organization: str,
    project: str,
    area_path: str,
    incluir_subpaths: bool = True,
    ativo: bool = True,
    intervalo_minutos: int = 60,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO area_paths
                (organization, project, area_path, incluir_subpaths, ativo, intervalo_minutos)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (organization, project, area_path, incluir_subpaths, ativo, intervalo_minutos),
        )
        return cur.fetchone()[0]


def list_area_paths(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM area_paths ORDER BY id")
        return cur.fetchall()


def get_area_path(conn: psycopg.Connection, area_path_id: int) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM area_paths WHERE id = %s", (area_path_id,))
        return cur.fetchone()


def update_area_path(conn: psycopg.Connection, area_path_id: int, **fields) -> None:
    if not fields:
        return
    columns = ", ".join(f"{key} = %s" for key in fields)
    values = list(fields.values()) + [area_path_id]
    with conn.cursor() as cur:
        cur.execute(f"UPDATE area_paths SET {columns} WHERE id = %s", values)


def delete_area_path(conn: psycopg.Connection, area_path_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sync_logs WHERE area_path_id = %s", (area_path_id,))
        cur.execute("DELETE FROM sync_checkpoints WHERE area_path_id = %s", (area_path_id,))
        cur.execute("DELETE FROM work_items WHERE area_path_id = %s", (area_path_id,))
        cur.execute("DELETE FROM area_paths WHERE id = %s", (area_path_id,))


def try_acquire_lock(conn: psycopg.Connection, area_path_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE area_paths SET is_running = TRUE WHERE id = %s AND is_running = FALSE RETURNING id",
            (area_path_id,),
        )
        return cur.fetchone() is not None


def release_lock(conn: psycopg.Connection, area_path_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE area_paths SET is_running = FALSE WHERE id = %s", (area_path_id,))


def update_sync_result(conn: psycopg.Connection, area_path_id: int, status: str, count: int, synced_at) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE area_paths
            SET last_sync_status = %s, last_sync_count = %s, last_sync_at = %s
            WHERE id = %s
            """,
            (status, count, synced_at, area_path_id),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_repository.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add app/repository.py tests/test_repository.py
git commit -m "feat: add area_paths CRUD and lock repository functions"
```

---

### Task 3: Work item, checkpoint, and sync_log repository functions

**Files:**
- Modify: `app/repository.py`
- Modify: `tests/test_repository.py`

**Interfaces:**
- Consumes: `create_area_path` (Task 2, used as test fixture data)
- Produces:
  - `get_checkpoint(conn, area_path_id) -> datetime | None`
  - `set_checkpoint(conn, area_path_id, changed_date) -> None`
  - `get_work_item_ids(conn, area_path_id) -> set[int]`
  - `upsert_work_items(conn, area_path_id, items: list[dict]) -> None` — each item dict has keys `id`, `title`, `work_item_type`, `state`, `assigned_to`, `changed_date`, `raw_json`
  - `delete_work_items(conn, area_path_id, ids: set[int]) -> None`
  - `create_sync_log(conn, area_path_id, started_at) -> int` (log id)
  - `finish_sync_log(conn, log_id, finished_at, status, items_processed, error_msg=None) -> None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_repository.py`:
```python
import datetime
import json


def _make_area_path(db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()
    return area_path_id


def test_checkpoint_roundtrip(db_conn):
    area_path_id = _make_area_path(db_conn)
    assert repo.get_checkpoint(db_conn, area_path_id) is None

    when = datetime.datetime(2026, 7, 15, 9, 30, 0)
    repo.set_checkpoint(db_conn, area_path_id, when)
    db_conn.commit()

    assert repo.get_checkpoint(db_conn, area_path_id) == when

    later = datetime.datetime(2026, 7, 16, 9, 30, 0)
    repo.set_checkpoint(db_conn, area_path_id, later)
    db_conn.commit()

    assert repo.get_checkpoint(db_conn, area_path_id) == later


def test_upsert_and_get_work_item_ids(db_conn):
    area_path_id = _make_area_path(db_conn)
    items = [
        {
            "id": 1,
            "title": "Bug A",
            "work_item_type": "Bug",
            "state": "Active",
            "assigned_to": "alice@example.com",
            "changed_date": datetime.datetime(2026, 7, 1),
            "raw_json": json.dumps({"id": 1}),
        },
        {
            "id": 2,
            "title": "Task B",
            "work_item_type": "Task",
            "state": "New",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 2),
            "raw_json": json.dumps({"id": 2}),
        },
    ]

    repo.upsert_work_items(db_conn, area_path_id, items)
    db_conn.commit()

    assert repo.get_work_item_ids(db_conn, area_path_id) == {1, 2}

    items[0]["title"] = "Bug A (renamed)"
    repo.upsert_work_items(db_conn, area_path_id, [items[0]])
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT title FROM work_items WHERE id = 1")
        assert cur.fetchone()[0] == "Bug A (renamed)"


def test_delete_work_items(db_conn):
    area_path_id = _make_area_path(db_conn)
    items = [
        {
            "id": 1,
            "title": "Bug A",
            "work_item_type": "Bug",
            "state": "Active",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 1),
            "raw_json": json.dumps({"id": 1}),
        },
        {
            "id": 2,
            "title": "Task B",
            "work_item_type": "Task",
            "state": "New",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 2),
            "raw_json": json.dumps({"id": 2}),
        },
    ]
    repo.upsert_work_items(db_conn, area_path_id, items)
    db_conn.commit()

    repo.delete_work_items(db_conn, area_path_id, {1})
    db_conn.commit()

    assert repo.get_work_item_ids(db_conn, area_path_id) == {2}


def test_sync_log_lifecycle(db_conn):
    area_path_id = _make_area_path(db_conn)
    started = datetime.datetime(2026, 7, 15, 10, 0, 0)

    log_id = repo.create_sync_log(db_conn, area_path_id, started)
    db_conn.commit()

    finished = datetime.datetime(2026, 7, 15, 10, 5, 0)
    repo.finish_sync_log(db_conn, log_id, finished, status="ok", items_processed=10)
    db_conn.commit()

    with db_conn.cursor(row_factory=repo.dict_row) as cur:
        cur.execute("SELECT * FROM sync_logs WHERE id = %s", (log_id,))
        row = cur.fetchone()

    assert row["status"] == "ok"
    assert row["items_processed"] == 10
    assert row["finished_at"] == finished
    assert row["error_msg"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_repository.py -v`
Expected: FAIL with `AttributeError: module 'app.repository' has no attribute 'get_checkpoint'`

- [ ] **Step 3: Append work item / checkpoint / log functions to repository.py**

Append to `app/repository.py`:
```python
def get_checkpoint(conn: psycopg.Connection, area_path_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_changed_date FROM sync_checkpoints WHERE area_path_id = %s",
            (area_path_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def set_checkpoint(conn: psycopg.Connection, area_path_id: int, changed_date) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sync_checkpoints (area_path_id, last_changed_date)
            VALUES (%s, %s)
            ON CONFLICT (area_path_id) DO UPDATE SET last_changed_date = EXCLUDED.last_changed_date
            """,
            (area_path_id, changed_date),
        )


def get_work_item_ids(conn: psycopg.Connection, area_path_id: int) -> set[int]:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM work_items WHERE area_path_id = %s", (area_path_id,))
        return {row[0] for row in cur.fetchall()}


def upsert_work_items(conn: psycopg.Connection, area_path_id: int, items: list[dict]) -> None:
    if not items:
        return
    with conn.cursor() as cur:
        for item in items:
            cur.execute(
                """
                INSERT INTO work_items
                    (id, area_path_id, title, work_item_type, state, assigned_to, changed_date, raw_json, synced_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (id) DO UPDATE SET
                    area_path_id = EXCLUDED.area_path_id,
                    title = EXCLUDED.title,
                    work_item_type = EXCLUDED.work_item_type,
                    state = EXCLUDED.state,
                    assigned_to = EXCLUDED.assigned_to,
                    changed_date = EXCLUDED.changed_date,
                    raw_json = EXCLUDED.raw_json,
                    synced_at = now()
                """,
                (
                    item["id"],
                    area_path_id,
                    item["title"],
                    item["work_item_type"],
                    item["state"],
                    item["assigned_to"],
                    item["changed_date"],
                    item["raw_json"],
                ),
            )


def delete_work_items(conn: psycopg.Connection, area_path_id: int, ids: set[int]) -> None:
    if not ids:
        return
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM work_items WHERE area_path_id = %s AND id = ANY(%s)",
            (area_path_id, list(ids)),
        )


def create_sync_log(conn: psycopg.Connection, area_path_id: int, started_at) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sync_logs (area_path_id, started_at) VALUES (%s, %s) RETURNING id",
            (area_path_id, started_at),
        )
        return cur.fetchone()[0]


def finish_sync_log(
    conn: psycopg.Connection,
    log_id: int,
    finished_at,
    status: str,
    items_processed: int,
    error_msg: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE sync_logs
            SET finished_at = %s, status = %s, items_processed = %s, error_msg = %s
            WHERE id = %s
            """,
            (finished_at, status, items_processed, error_msg, log_id),
        )
```

Add the `dict_row` import at the top of `app/repository.py` if not already present (it was added in Task 2's `from psycopg.rows import dict_row`) — reuse that import, no change needed there.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_repository.py -v`
Expected: PASS (12 tests total)

- [ ] **Step 5: Commit**

```bash
git add app/repository.py tests/test_repository.py
git commit -m "feat: add work item, checkpoint, and sync log repository functions"
```

---

### Task 4: Azure DevOps REST client with retry

**Files:**
- Create: `app/ado_client.py`
- Test: `tests/test_ado_client.py`

**Interfaces:**
- Consumes: `app.config.get_ado_api_key` (Task 1)
- Produces:
  - `class AdoAuthError(Exception)`
  - `class AdoRetryExhaustedError(Exception)`
  - `class AdoClient:`
    - `__init__(self, organization: str, project: str, pat: str | None = None)`
    - `get_all_ids(self, area_path: str, incluir_subpaths: bool) -> list[int]`
    - `get_changed_ids(self, area_path: str, incluir_subpaths: bool, since=None) -> list[int]`
    - `get_work_items_batch(self, ids: list[int]) -> list[dict]` — each dict has keys `id`, `title`, `work_item_type`, `state`, `assigned_to`, `changed_date` (as `datetime`), `raw_json` (as JSON string) — matching exactly what `repository.upsert_work_items` expects.
  - Module constant `RETRY_DELAYS = [5, 15, 30]`

- [ ] **Step 1: Write the failing tests**

`tests/test_ado_client.py`:
```python
import datetime
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.ado_client import AdoAuthError, AdoClient, AdoRetryExhaustedError


def _response(status_code, json_body=None, headers=None):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.headers = headers or {}
    return resp


@patch("app.ado_client.requests.post")
def test_get_all_ids_uses_under_operator_when_subpaths_true(mock_post):
    mock_post.return_value = _response(200, {"workItems": [{"id": 1}, {"id": 2}]})

    client = AdoClient("org", "proj", pat="fake-pat")
    ids = client.get_all_ids("proj\\Team A", incluir_subpaths=True)

    assert ids == [1, 2]
    sent_query = mock_post.call_args.kwargs["json"]["query"]
    assert "UNDER 'proj\\Team A'" in sent_query


@patch("app.ado_client.requests.post")
def test_get_all_ids_uses_equals_operator_when_subpaths_false(mock_post):
    mock_post.return_value = _response(200, {"workItems": []})

    client = AdoClient("org", "proj", pat="fake-pat")
    client.get_all_ids("proj\\Team A", incluir_subpaths=False)

    sent_query = mock_post.call_args.kwargs["json"]["query"]
    assert "[System.AreaPath] = 'proj\\Team A'" in sent_query


@patch("app.ado_client.requests.post")
def test_get_changed_ids_includes_changed_date_filter(mock_post):
    mock_post.return_value = _response(200, {"workItems": []})

    client = AdoClient("org", "proj", pat="fake-pat")
    since = datetime.datetime(2026, 7, 1, 12, 0, 0)
    client.get_changed_ids("proj\\Team A", incluir_subpaths=True, since=since)

    sent_query = mock_post.call_args.kwargs["json"]["query"]
    assert "[System.ChangedDate] > '2026-07-01 12:00:00'" in sent_query


@patch("app.ado_client.requests.post")
def test_get_changed_ids_without_since_has_no_date_filter(mock_post):
    mock_post.return_value = _response(200, {"workItems": []})

    client = AdoClient("org", "proj", pat="fake-pat")
    client.get_changed_ids("proj\\Team A", incluir_subpaths=True, since=None)

    sent_query = mock_post.call_args.kwargs["json"]["query"]
    assert "ChangedDate" not in sent_query


@patch("app.ado_client.requests.post")
def test_get_work_items_batch_maps_fields(mock_post):
    mock_post.return_value = _response(
        200,
        {
            "value": [
                {
                    "id": 1,
                    "fields": {
                        "System.Title": "Bug A",
                        "System.WorkItemType": "Bug",
                        "System.State": "Active",
                        "System.AssignedTo": {"displayName": "Alice", "uniqueName": "alice@example.com"},
                        "System.ChangedDate": "2026-07-01T12:00:00Z",
                    },
                }
            ]
        },
    )

    client = AdoClient("org", "proj", pat="fake-pat")
    items = client.get_work_items_batch([1])

    assert len(items) == 1
    item = items[0]
    assert item["id"] == 1
    assert item["title"] == "Bug A"
    assert item["work_item_type"] == "Bug"
    assert item["state"] == "Active"
    assert item["assigned_to"] == "alice@example.com"
    assert item["changed_date"] == datetime.datetime(2026, 7, 1, 12, 0, 0)
    assert json.loads(item["raw_json"])["id"] == 1


@patch("app.ado_client.requests.post")
def test_401_raises_auth_error_without_retry(mock_post):
    mock_post.return_value = _response(401)

    client = AdoClient("org", "proj", pat="bad-pat")
    with pytest.raises(AdoAuthError):
        client.get_all_ids("proj\\A", incluir_subpaths=True)

    assert mock_post.call_count == 1


@patch("app.ado_client.time.sleep")
@patch("app.ado_client.requests.post")
def test_429_retries_with_fixed_delays_then_succeeds(mock_post, mock_sleep):
    mock_post.side_effect = [
        _response(429),
        _response(429),
        _response(200, {"workItems": [{"id": 1}]}),
    ]

    client = AdoClient("org", "proj", pat="fake-pat")
    ids = client.get_all_ids("proj\\A", incluir_subpaths=True)

    assert ids == [1]
    assert mock_sleep.call_args_list == [((5,),), ((15,),)]


@patch("app.ado_client.time.sleep")
@patch("app.ado_client.requests.post")
def test_429_exhausts_retries_and_raises(mock_post, mock_sleep):
    mock_post.side_effect = [_response(429), _response(429), _response(429)]

    client = AdoClient("org", "proj", pat="fake-pat")
    with pytest.raises(AdoRetryExhaustedError):
        client.get_all_ids("proj\\A", incluir_subpaths=True)

    assert mock_sleep.call_args_list == [((5,),), ((15,),), ((30,),)]


@patch("app.ado_client.time.sleep")
@patch("app.ado_client.requests.post")
def test_retry_after_header_overrides_default_delay(mock_post, mock_sleep):
    mock_post.side_effect = [
        _response(429, headers={"Retry-After": "20"}),
        _response(200, {"workItems": []}),
    ]

    client = AdoClient("org", "proj", pat="fake-pat")
    client.get_all_ids("proj\\A", incluir_subpaths=True)

    mock_sleep.assert_called_once_with(20)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ado_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ado_client'`

- [ ] **Step 3: Write ado_client.py**

`app/ado_client.py`:
```python
import datetime
import json
import time

import requests

from app.config import get_ado_api_key

RETRY_DELAYS = [5, 15, 30]
API_VERSION = "7.1"


class AdoAuthError(Exception):
    pass


class AdoRetryExhaustedError(Exception):
    pass


class AdoClient:
    def __init__(self, organization: str, project: str, pat: str | None = None):
        self.organization = organization
        self.project = project
        self.pat = pat or get_ado_api_key()

    def _auth(self):
        return ("", self.pat)

    def _post_with_retry(self, url: str, json_body: dict) -> dict:
        last_status = None
        for attempt, delay in enumerate([0, *RETRY_DELAYS]):
            if delay:
                time.sleep(delay)

            response = requests.post(url, json=json_body, auth=self._auth())

            if response.status_code == 401:
                raise AdoAuthError(f"Azure DevOps rejected credentials (401) calling {url}")

            if response.status_code in (429, 500, 502, 503, 504):
                last_status = response.status_code
                retry_after = response.headers.get("Retry-After")
                if retry_after and attempt < len(RETRY_DELAYS):
                    RETRY_DELAYS_FOR_THIS_CALL = list(RETRY_DELAYS)
                    RETRY_DELAYS_FOR_THIS_CALL[attempt] = int(retry_after)
                    if int(retry_after) > (RETRY_DELAYS[attempt] if attempt < len(RETRY_DELAYS) else 0):
                        time.sleep(int(retry_after) - delay if delay else int(retry_after))
                continue

            response.raise_for_status()
            return response.json()

        raise AdoRetryExhaustedError(
            f"Exhausted retries calling {url}, last status={last_status}"
        )

    def _wiql_query(self, query: str) -> list[int]:
        url = f"https://dev.azure.com/{self.organization}/{self.project}/_apis/wit/wiql?api-version={API_VERSION}"
        body = self._post_with_retry(url, {"query": query})
        return [item["id"] for item in body.get("workItems", [])]

    def get_all_ids(self, area_path: str, incluir_subpaths: bool) -> list[int]:
        operator = "UNDER" if incluir_subpaths else "="
        query = (
            "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = "
            f"'{self.project}' AND [System.AreaPath] {operator} '{area_path}'"
        )
        return self._wiql_query(query)

    def get_changed_ids(self, area_path: str, incluir_subpaths: bool, since=None) -> list[int]:
        operator = "UNDER" if incluir_subpaths else "="
        query = (
            "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = "
            f"'{self.project}' AND [System.AreaPath] {operator} '{area_path}'"
        )
        if since is not None:
            query += f" AND [System.ChangedDate] > '{since.strftime('%Y-%m-%d %H:%M:%S')}'"
        return self._wiql_query(query)

    def get_work_items_batch(self, ids: list[int]) -> list[dict]:
        if not ids:
            return []

        url = f"https://dev.azure.com/{self.organization}/_apis/wit/workitemsbatch?api-version={API_VERSION}"
        fields = [
            "System.Title",
            "System.WorkItemType",
            "System.State",
            "System.AssignedTo",
            "System.ChangedDate",
        ]

        results = []
        for start in range(0, len(ids), 200):
            chunk = ids[start : start + 200]
            body = self._post_with_retry(url, {"ids": chunk, "fields": fields})
            for raw in body.get("value", []):
                results.append(self._map_work_item(raw))
        return results

    @staticmethod
    def _map_work_item(raw: dict) -> dict:
        fields = raw.get("fields", {})
        assigned_to_field = fields.get("System.AssignedTo")
        assigned_to = None
        if isinstance(assigned_to_field, dict):
            assigned_to = assigned_to_field.get("uniqueName")
        elif isinstance(assigned_to_field, str):
            assigned_to = assigned_to_field

        changed_date_raw = fields.get("System.ChangedDate")
        changed_date = None
        if changed_date_raw:
            changed_date = datetime.datetime.strptime(
                changed_date_raw.split(".")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S"
            )

        return {
            "id": raw["id"],
            "title": fields.get("System.Title"),
            "work_item_type": fields.get("System.WorkItemType"),
            "state": fields.get("System.State"),
            "assigned_to": assigned_to,
            "changed_date": changed_date,
            "raw_json": json.dumps(raw),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ado_client.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add app/ado_client.py tests/test_ado_client.py
git commit -m "feat: add Azure DevOps REST client with fixed-delay retry"
```

---

### Task 5: Sync service (full/delta orchestration, deletion, lock, logging)

**Files:**
- Create: `app/sync_service.py`
- Test: `tests/test_sync_service.py`

**Interfaces:**
- Consumes:
  - `repository.try_acquire_lock/release_lock/get_checkpoint/set_checkpoint/get_work_item_ids/upsert_work_items/delete_work_items/create_sync_log/finish_sync_log/update_sync_result` (Tasks 2–3)
  - `ado_client.AdoClient`, `AdoAuthError`, `AdoRetryExhaustedError` (Task 4)
- Produces:
  - `run_sync(conn, area_path_row: dict, client: AdoClient) -> dict` with keys `status` (`"ok" | "auth_error" | "error" | "skipped_running"`), `items_processed` (int)

`area_path_row` is a dict shaped like the rows from `repository.get_area_path` (`id`, `organization`, `project`, `area_path`, `incluir_subpaths`, ...).

- [ ] **Step 1: Write the failing tests**

`tests/test_sync_service.py`:
```python
import datetime
from unittest.mock import MagicMock

from app import repository as repo
from app import sync_service
from app.ado_client import AdoAuthError, AdoRetryExhaustedError


def _area_path_row(db_conn, incluir_subpaths=True):
    area_path_id = repo.create_area_path(
        db_conn, "org", "proj", "proj\\A", incluir_subpaths=incluir_subpaths
    )
    db_conn.commit()
    return repo.get_area_path(db_conn, area_path_id)


def test_full_load_upserts_all_items_and_sets_checkpoint(db_conn):
    row = _area_path_row(db_conn)
    client = MagicMock()
    client.get_all_ids.return_value = [1, 2]
    client.get_changed_ids.return_value = [1, 2]
    client.get_work_items_batch.return_value = [
        {
            "id": 1,
            "title": "A",
            "work_item_type": "Bug",
            "state": "Active",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 1),
            "raw_json": "{}",
        },
        {
            "id": 2,
            "title": "B",
            "work_item_type": "Task",
            "state": "New",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 2),
            "raw_json": "{}",
        },
    ]

    result = sync_service.run_sync(db_conn, row, client)
    db_conn.commit()

    assert result["status"] == "ok"
    assert result["items_processed"] == 2
    assert repo.get_work_item_ids(db_conn, row["id"]) == {1, 2}
    assert repo.get_checkpoint(db_conn, row["id"]) == datetime.datetime(2026, 7, 2)
    assert repo.get_area_path(db_conn, row["id"])["is_running"] is False


def test_delta_deletes_items_no_longer_in_scope(db_conn):
    row = _area_path_row(db_conn)
    repo.upsert_work_items(
        db_conn,
        row["id"],
        [
            {
                "id": 1,
                "title": "A",
                "work_item_type": "Bug",
                "state": "Active",
                "assigned_to": None,
                "changed_date": datetime.datetime(2026, 7, 1),
                "raw_json": "{}",
            },
            {
                "id": 2,
                "title": "B",
                "work_item_type": "Task",
                "state": "New",
                "assigned_to": None,
                "changed_date": datetime.datetime(2026, 7, 2),
                "raw_json": "{}",
            },
        ],
    )
    repo.set_checkpoint(db_conn, row["id"], datetime.datetime(2026, 7, 2))
    db_conn.commit()
    row = repo.get_area_path(db_conn, row["id"])

    client = MagicMock()
    client.get_all_ids.return_value = [2]  # item 1 no longer exists / moved out
    client.get_changed_ids.return_value = []
    client.get_work_items_batch.return_value = []

    result = sync_service.run_sync(db_conn, row, client)
    db_conn.commit()

    assert result["status"] == "ok"
    assert repo.get_work_item_ids(db_conn, row["id"]) == {2}


def test_skips_when_already_running(db_conn):
    row = _area_path_row(db_conn)
    repo.try_acquire_lock(db_conn, row["id"])
    db_conn.commit()
    row = repo.get_area_path(db_conn, row["id"])

    client = MagicMock()
    result = sync_service.run_sync(db_conn, row, client)

    assert result["status"] == "skipped_running"
    client.get_all_ids.assert_not_called()


def test_auth_error_sets_status_and_releases_lock(db_conn):
    row = _area_path_row(db_conn)
    client = MagicMock()
    client.get_all_ids.side_effect = AdoAuthError("bad token")

    result = sync_service.run_sync(db_conn, row, client)
    db_conn.commit()

    assert result["status"] == "auth_error"
    assert repo.get_area_path(db_conn, row["id"])["last_sync_status"] == "auth_error"
    assert repo.get_area_path(db_conn, row["id"])["is_running"] is False


def test_retry_exhausted_sets_error_status(db_conn):
    row = _area_path_row(db_conn)
    client = MagicMock()
    client.get_all_ids.side_effect = AdoRetryExhaustedError("gave up")

    result = sync_service.run_sync(db_conn, row, client)
    db_conn.commit()

    assert result["status"] == "error"
    assert repo.get_area_path(db_conn, row["id"])["last_sync_status"] == "error"
    assert repo.get_area_path(db_conn, row["id"])["is_running"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sync_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.sync_service'`

- [ ] **Step 3: Write sync_service.py**

`app/sync_service.py`:
```python
import datetime

from app import repository as repo
from app.ado_client import AdoAuthError, AdoClient, AdoRetryExhaustedError


def run_sync(conn, area_path_row: dict, client: AdoClient) -> dict:
    area_path_id = area_path_row["id"]

    if not repo.try_acquire_lock(conn, area_path_id):
        return {"status": "skipped_running", "items_processed": 0}
    conn.commit()

    started_at = datetime.datetime.now()
    log_id = repo.create_sync_log(conn, area_path_id, started_at)
    conn.commit()

    try:
        items_processed = _do_sync(conn, area_path_row, client)
        finished_at = datetime.datetime.now()
        repo.finish_sync_log(conn, log_id, finished_at, status="ok", items_processed=items_processed)
        repo.update_sync_result(conn, area_path_id, status="ok", count=items_processed, synced_at=finished_at)
        conn.commit()
        return {"status": "ok", "items_processed": items_processed}

    except AdoAuthError as exc:
        return _fail(conn, area_path_id, log_id, "auth_error", str(exc))

    except AdoRetryExhaustedError as exc:
        return _fail(conn, area_path_id, log_id, "error", str(exc))

    except Exception as exc:  # unexpected error: still release lock and record it
        return _fail(conn, area_path_id, log_id, "error", str(exc))

    finally:
        repo.release_lock(conn, area_path_id)
        conn.commit()


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

    return len(items)


def _fail(conn, area_path_id: int, log_id: int, status: str, error_msg: str) -> dict:
    finished_at = datetime.datetime.now()
    repo.finish_sync_log(conn, log_id, finished_at, status=status, items_processed=0, error_msg=error_msg)
    repo.update_sync_result(conn, area_path_id, status=status, count=0, synced_at=finished_at)
    conn.commit()
    return {"status": status, "items_processed": 0}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sync_service.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add app/sync_service.py tests/test_sync_service.py
git commit -m "feat: add sync orchestration with lock, delta, deletion, and error handling"
```

---

### Task 6: Flask routes (CRUD + manual sync + auth banner)

**Files:**
- Create: `app/routes.py`
- Create: `app/templates/index.html`
- Create: `app/templates/area_path_form.html`
- Test: `tests/test_routes.py`

**Interfaces:**
- Consumes: `repository.*` (Tasks 2–3), `sync_service.run_sync` (Task 5), `ado_client.AdoClient` (Task 4)
- Produces:
  - `create_app(conn_factory=db.get_connection) -> Flask`
  - Routes:
    - `GET /` — list area paths + auth-error banner
    - `POST /area-paths` — create
    - `POST /area-paths/<int:area_path_id>/edit` — update
    - `POST /area-paths/<int:area_path_id>/delete` — delete
    - `POST /area-paths/<int:area_path_id>/sync` — manual trigger; returns 409 if `is_running`

- [ ] **Step 1: Write the failing tests**

`tests/test_routes.py`:
```python
from unittest.mock import MagicMock, patch

import pytest

from app import repository as repo
from app.routes import create_app


@pytest.fixture
def client(db_conn):
    app = create_app(conn_factory=lambda: db_conn)
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_index_lists_area_paths(client, db_conn):
    repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()

    response = client.get("/")

    assert response.status_code == 200
    assert b"proj\\A" in response.data


def test_index_shows_auth_error_banner(client, db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    repo.update_area_path(db_conn, area_path_id, last_sync_status="auth_error")
    db_conn.commit()

    response = client.get("/")

    assert b"AZURE_DEVOPS_API_KEY" in response.data


def test_create_area_path(client, db_conn):
    response = client.post(
        "/area-paths",
        data={
            "organization": "org",
            "project": "proj",
            "area_path": "proj\\B",
            "incluir_subpaths": "on",
            "ativo": "on",
            "intervalo_minutos": "45",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    rows = repo.list_area_paths(db_conn)
    assert len(rows) == 1
    assert rows[0]["area_path"] == "proj\\B"
    assert rows[0]["intervalo_minutos"] == 45


def test_delete_area_path(client, db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()

    client.post(f"/area-paths/{area_path_id}/delete", follow_redirects=True)

    assert repo.get_area_path(db_conn, area_path_id) is None


@patch("app.routes.AdoClient")
@patch("app.routes.sync_service.run_sync")
def test_manual_sync_triggers_run_sync(mock_run_sync, mock_ado_client, client, db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()
    mock_run_sync.return_value = {"status": "ok", "items_processed": 3}

    response = client.post(f"/area-paths/{area_path_id}/sync", follow_redirects=True)

    assert response.status_code == 200
    mock_run_sync.assert_called_once()


def test_manual_sync_returns_409_when_already_running(client, db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()
    repo.try_acquire_lock(db_conn, area_path_id)
    db_conn.commit()

    response = client.post(f"/area-paths/{area_path_id}/sync")

    assert response.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_routes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.routes'`

- [ ] **Step 3: Write templates**

`app/templates/index.html`:
```html
<!doctype html>
<html>
<head><title>Azure DevOps Sync</title></head>
<body>
  {% if auth_error %}
    <div style="background:#fdd;color:#900;padding:10px;border:1px solid #900;">
      Token inválido/expirado — verifique AZURE_DEVOPS_API_KEY
    </div>
  {% endif %}

  <h1>Area Paths</h1>
  <table border="1" cellpadding="4">
    <tr>
      <th>Org</th><th>Project</th><th>Area Path</th><th>Sub-paths</th>
      <th>Ativo</th><th>Intervalo (min)</th><th>Última sync</th>
      <th>Status</th><th>Qtd processada</th><th>Ações</th>
    </tr>
    {% for row in area_paths %}
    <tr>
      <td>{{ row.organization }}</td>
      <td>{{ row.project }}</td>
      <td>{{ row.area_path }}</td>
      <td>{{ "Sim" if row.incluir_subpaths else "Não" }}</td>
      <td>{{ "Sim" if row.ativo else "Não" }}</td>
      <td>{{ row.intervalo_minutos }}</td>
      <td>{{ row.last_sync_at or "-" }}</td>
      <td>{{ row.last_sync_status or "-" }}</td>
      <td>{{ row.last_sync_count or 0 }}</td>
      <td>
        <form method="post" action="/area-paths/{{ row.id }}/sync" style="display:inline">
          <button type="submit" {{ "disabled" if row.is_running else "" }}>Sincronizar agora</button>
        </form>
        <form method="post" action="/area-paths/{{ row.id }}/delete" style="display:inline">
          <button type="submit">Excluir</button>
        </form>
      </td>
    </tr>
    {% endfor %}
  </table>

  <h2>Novo Area Path</h2>
  {% include "area_path_form.html" %}
</body>
</html>
```

`app/templates/area_path_form.html`:
```html
<form method="post" action="/area-paths">
  <label>Organization: <input name="organization" required></label><br>
  <label>Project: <input name="project" required></label><br>
  <label>Area Path: <input name="area_path" required></label><br>
  <label>Incluir sub-paths: <input type="checkbox" name="incluir_subpaths" checked></label><br>
  <label>Ativo: <input type="checkbox" name="ativo" checked></label><br>
  <label>Intervalo (minutos): <input type="number" name="intervalo_minutos" value="60"></label><br>
  <button type="submit">Salvar</button>
</form>
```

- [ ] **Step 4: Write routes.py**

`app/routes.py`:
```python
from flask import Flask, redirect, render_template, request

from app import db, repository as repo, sync_service
from app.ado_client import AdoClient


def create_app(conn_factory=db.get_connection) -> Flask:
    app = Flask(__name__)

    @app.route("/", methods=["GET"])
    def index():
        conn = conn_factory()
        rows = repo.list_area_paths(conn)
        auth_error = any(row["last_sync_status"] == "auth_error" for row in rows)
        return render_template("index.html", area_paths=rows, auth_error=auth_error)

    @app.route("/area-paths", methods=["POST"])
    def create_area_path():
        conn = conn_factory()
        repo.create_area_path(
            conn,
            organization=request.form["organization"],
            project=request.form["project"],
            area_path=request.form["area_path"],
            incluir_subpaths=request.form.get("incluir_subpaths") == "on",
            ativo=request.form.get("ativo") == "on",
            intervalo_minutos=int(request.form.get("intervalo_minutos", 60)),
        )
        conn.commit()
        return redirect("/")

    @app.route("/area-paths/<int:area_path_id>/edit", methods=["POST"])
    def edit_area_path(area_path_id):
        conn = conn_factory()
        repo.update_area_path(
            conn,
            area_path_id,
            organization=request.form["organization"],
            project=request.form["project"],
            area_path=request.form["area_path"],
            incluir_subpaths=request.form.get("incluir_subpaths") == "on",
            ativo=request.form.get("ativo") == "on",
            intervalo_minutos=int(request.form.get("intervalo_minutos", 60)),
        )
        conn.commit()
        return redirect("/")

    @app.route("/area-paths/<int:area_path_id>/delete", methods=["POST"])
    def delete_area_path(area_path_id):
        conn = conn_factory()
        repo.delete_area_path(conn, area_path_id)
        conn.commit()
        return redirect("/")

    @app.route("/area-paths/<int:area_path_id>/sync", methods=["POST"])
    def manual_sync(area_path_id):
        conn = conn_factory()
        row = repo.get_area_path(conn, area_path_id)
        if row["is_running"]:
            return {"error": "sync already running"}, 409

        client = AdoClient(row["organization"], row["project"])
        result = sync_service.run_sync(conn, row, client)
        return redirect("/")

    return app
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_routes.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add app/routes.py app/templates tests/test_routes.py
git commit -m "feat: add Flask CRUD routes, manual sync trigger, and auth-error banner"
```

---

### Task 7: Scheduler wiring

**Files:**
- Create: `app/scheduler.py`

**Interfaces:**
- Consumes: `repository.list_area_paths`, `sync_service.run_sync`, `ado_client.AdoClient`, `db.get_connection`
- Produces: `build_scheduler(conn_factory=db.get_connection) -> apscheduler.schedulers.background.BackgroundScheduler`

Each active area path gets its own interval job (re-read from DB on every tick, so edits to `intervalo_minutos`/`ativo` take effect on the next tick without restarting the app). No unit test here — APScheduler's own timing is out of scope to unit-test; this task is verified manually in Task 9's smoke test. Keeping this untested is intentional: the only logic here is "read active rows, call run_sync", already covered by Task 5/6 tests.

- [ ] **Step 1: Write scheduler.py**

`app/scheduler.py`:
```python
from apscheduler.schedulers.background import BackgroundScheduler

from app import db, repository as repo, sync_service
from app.ado_client import AdoClient

JOB_ID_PREFIX = "sync-area-path-"


def _sync_all_active(conn_factory):
    conn = conn_factory()
    for row in repo.list_area_paths(conn):
        if not row["ativo"]:
            continue
        client = AdoClient(row["organization"], row["project"])
        sync_service.run_sync(conn, row, client)


def build_scheduler(conn_factory=db.get_connection) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _sync_all_active,
        "interval",
        minutes=1,
        args=[conn_factory],
        id="sync-tick",
        replace_existing=True,
    )
    return scheduler
```

Note: the scheduler ticks every minute and, for each active area path, `run_sync` re-checks `is_running` via `try_acquire_lock` — so an area path with `intervalo_minutos=60` still only gets its expensive WIQL/batch calls run once triggered, but this simple design re-evaluates every minute. Since `run_sync` is idempotent and lock-guarded, the only cost of a 1-minute tick is a cheap `list_area_paths` call; to actually respect `intervalo_minutos` precisely, compare `last_sync_at + intervalo_minutos` against now before calling `run_sync`. Fold that check into `_sync_all_active` now:

- [ ] **Step 2: Add interval check to _sync_all_active**

Replace the function in `app/scheduler.py`:
```python
import datetime


def _sync_all_active(conn_factory):
    conn = conn_factory()
    now = datetime.datetime.now()
    for row in repo.list_area_paths(conn):
        if not row["ativo"]:
            continue
        if row["last_sync_at"]:
            due_at = row["last_sync_at"] + datetime.timedelta(minutes=row["intervalo_minutos"])
            if now < due_at:
                continue
        client = AdoClient(row["organization"], row["project"])
        sync_service.run_sync(conn, row, client)
```

Move the `import datetime` to the top of the file with the other imports instead of inline.

- [ ] **Step 3: Commit**

```bash
git add app/scheduler.py
git commit -m "feat: add interval-respecting background scheduler"
```

---

### Task 8: App entrypoint + README

**Files:**
- Create: `run.py`
- Create: `README.md`

**Interfaces:**
- Consumes: `app.routes.create_app`, `app.scheduler.build_scheduler`, `app.db.init_schema`, `app.db.get_connection`

- [ ] **Step 1: Write run.py**

`run.py`:
```python
from app import db
from app.routes import create_app
from app.scheduler import build_scheduler

conn = db.get_connection()
db.init_schema(conn)
conn.commit()
conn.close()

app = create_app()
scheduler = build_scheduler()
scheduler.start()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
```

- [ ] **Step 2: Write README.md**

`README.md`:
```markdown
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
```

- [ ] **Step 3: Commit**

```bash
git add run.py README.md
git commit -m "feat: add app entrypoint and README"
```

---

### Task 9: Manual smoke test

**Files:** none (verification only)

- [ ] **Step 1: Set env vars and start the app**

```
set DATABASE_URL=postgresql://postgres:postgres@localhost:5432/azure_sync
set AZURE_DEVOPS_API_KEY=<real PAT>
python run.py
```

- [ ] **Step 2: In a browser, open http://127.0.0.1:5000 and create an area path**

Use a real `organization`/`project`/`area_path` you have access to. Set `intervalo_minutos` low (e.g. `5`) to see the scheduler pick it up quickly.

- [ ] **Step 3: Click "Sincronizar agora" and confirm**

- Button becomes disabled while running (reload page during sync).
- After completion, "última sync", "status", and "quantidade processada" update.
- Rows appear in the `work_items` table (`psql -c "select count(*) from work_items;"`).

- [ ] **Step 4: Test deletion handling**

Close/delete a work item in Azure DevOps that was previously synced, or move it to a different area path. Trigger another manual sync and confirm the row disappears from `work_items`.

- [ ] **Step 5: Test auth error banner**

Temporarily set `AZURE_DEVOPS_API_KEY` to an invalid value, restart the app, trigger a sync, and confirm the red banner appears on `/`.

- [ ] **Step 6: Test lock**

Trigger a manual sync on an area path with a large enough backlog to take a few seconds, and immediately click "Sincronizar agora" again (or POST directly) — confirm it returns 409 / stays disabled.
