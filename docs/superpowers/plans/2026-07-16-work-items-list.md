# Work Items List (required area path, unified search, display-name Assigned To) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the work items list show the assignee's display name (not email), require an area path filter (auto-selecting the first one), and replace the separate Type filter with a single search field covering ID/Title/Type/State/Assigned To.

**Architecture:** Three independently testable layers, done bottom-up: (1) `sync-service` maps `displayName` instead of `uniqueName` for new/updated items, plus a one-off backfill script for existing rows using the already-stored `raw_json`; (2) `api-read`'s `repository.py`/`routes.py` make `area_path_id` required and add a `search` parameter that ORs an `ILIKE` across five columns; (3) `web-read` auto-selects the first area path, removes the Type filter, and adds a single Search input wired to the new `search` param.

**Tech Stack:** Python 3.11 / Flask / psycopg (raw SQL) for `sync-service` and `api-read`; TypeScript / React / Vite / `@astryxdesign` component library for `web-read`; pytest for backend tests.

## Global Constraints

- `repository.py` in `apps/api-read` must contain only SELECT statements — enforced by `apps/api-read/tests/test_readonly_guardrail.py` (regex-forbids INSERT/UPDATE/DELETE/UPSERT anywhere under `apps/api-read/app/*.py`).
- `apps/sync-service` is the only app allowed to write to the database (see `docs/adr/0002-single-writer.md`) — the backfill script lives under `apps/sync-service/`, not `apps/api-read/`.
- Work items list stays ordered by Changed Date, newest first (already the default — do not change `order_by`/`order_dir` defaults).
- No schema changes — `assigned_to` stays `TEXT`.

---

### Task 1: sync-service — map `displayName` instead of `uniqueName` for Assigned To

**Files:**
- Modify: `apps/sync-service/app/ado_client.py:128-137` (the `_map_work_item` static method)
- Test: `apps/sync-service/tests/test_ado_client.py:65-99` (`test_get_work_items_batch_maps_fields`)

**Interfaces:**
- Produces: `AdoClient._map_work_item(raw: dict) -> dict` still returns a dict with key `"assigned_to"`, but the value now comes from `fields["System.AssignedTo"]["displayName"]` instead of `["uniqueName"]`. No signature change — later tasks only depend on the `assigned_to` key existing in that dict, which is unchanged.

- [ ] **Step 1: Update the existing test to assert on `displayName`**

In `apps/sync-service/tests/test_ado_client.py`, the mock fields at line 77 already include both `displayName` and `uniqueName`:

```python
"System.AssignedTo": {"displayName": "Alice", "uniqueName": "alice@example.com"},
```

Change the assertion at line 95 from:

```python
    assert item["assigned_to"] == "alice@example.com"
```

to:

```python
    assert item["assigned_to"] == "Alice"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/sync-service && python -m pytest tests/test_ado_client.py::test_get_work_items_batch_maps_fields -v`
Expected: FAIL — `assert 'alice@example.com' == 'Alice'`

- [ ] **Step 3: Update `_map_work_item` to read `displayName`**

In `apps/sync-service/app/ado_client.py`, change:

```python
        if isinstance(assigned_to_field, dict):
            assigned_to = assigned_to_field.get("uniqueName")
```

to:

```python
        if isinstance(assigned_to_field, dict):
            assigned_to = assigned_to_field.get("displayName")
```

(The `elif isinstance(assigned_to_field, str): assigned_to = assigned_to_field` branch stays unchanged — it's a fallback for the rare case ADO returns a bare string instead of a dict.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/sync-service && python -m pytest tests/test_ado_client.py -v`
Expected: PASS (all tests in the file, including the one just changed)

- [ ] **Step 5: Commit**

```bash
git add apps/sync-service/app/ado_client.py apps/sync-service/tests/test_ado_client.py
git commit -m "fix(sync-service): map Assigned To display name instead of email"
```

---

### Task 2: sync-service — one-off backfill script for existing `assigned_to` values

**Files:**
- Create: `apps/sync-service/scripts/backfill_assigned_to_display_name.py`
- Create: `apps/sync-service/scripts/__init__.py` (empty, so the script's helper function is importable in tests)
- Test: `apps/sync-service/tests/test_backfill_assigned_to_display_name.py`

**Interfaces:**
- Consumes: `apps.db.get_connection()` (existing, from `apps/sync-service/app/db.py:71-72`, no args, returns `psycopg.Connection`).
- Produces: a module-level function `extract_display_name(raw_json: str) -> str | None` (pure, testable without a DB) and a `run(conn: psycopg.Connection) -> int` function (returns count of rows updated) that later ops/runbook steps invoke via `if __name__ == "__main__":`.

- [ ] **Step 1: Write the failing test for `extract_display_name`**

Create `apps/sync-service/tests/test_backfill_assigned_to_display_name.py`:

```python
import json

from scripts.backfill_assigned_to_display_name import extract_display_name


def test_extract_display_name_from_dict_field():
    raw = json.dumps(
        {"fields": {"System.AssignedTo": {"displayName": "Alice", "uniqueName": "alice@example.com"}}}
    )
    assert extract_display_name(raw) == "Alice"


def test_extract_display_name_returns_none_when_unassigned():
    raw = json.dumps({"fields": {}})
    assert extract_display_name(raw) is None


def test_extract_display_name_handles_string_field():
    raw = json.dumps({"fields": {"System.AssignedTo": "Bob"}})
    assert extract_display_name(raw) == "Bob"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/sync-service && python -m pytest tests/test_backfill_assigned_to_display_name.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts'`

- [ ] **Step 3: Create `apps/sync-service/scripts/__init__.py`**

Empty file:

```python
```

- [ ] **Step 4: Write the backfill script**

Create `apps/sync-service/scripts/backfill_assigned_to_display_name.py`:

```python
"""One-off backfill: repopulate work_items.assigned_to from the displayName
already present in each row's raw_json, instead of the uniqueName (email)
that earlier syncs stored there.

No calls to the Azure DevOps API — raw_json already contains the original
payload, so this is a pure local data migration.

Run once, after deploying the ado_client.py displayName fix:
    cd apps/sync-service
    python -m scripts.backfill_assigned_to_display_name
"""

import json

from app import db

BATCH_SIZE = 200


def extract_display_name(raw_json: str) -> str | None:
    raw = json.loads(raw_json)
    assigned_to_field = raw.get("fields", {}).get("System.AssignedTo")
    if isinstance(assigned_to_field, dict):
        return assigned_to_field.get("displayName")
    if isinstance(assigned_to_field, str):
        return assigned_to_field
    return None


def run(conn) -> int:
    updated = 0
    with conn.cursor(name="backfill_assigned_to") as read_cur:
        read_cur.execute(
            "SELECT id, raw_json, assigned_to FROM work_items WHERE raw_json IS NOT NULL"
        )
        with conn.cursor() as write_cur:
            for work_item_id, raw_json, current_assigned_to in read_cur:
                display_name = extract_display_name(json.dumps(raw_json))
                if display_name != current_assigned_to:
                    write_cur.execute(
                        "UPDATE work_items SET assigned_to = %s WHERE id = %s",
                        (display_name, work_item_id),
                    )
                    updated += 1
                    if updated % BATCH_SIZE == 0:
                        conn.commit()
    conn.commit()
    return updated


if __name__ == "__main__":
    connection = db.get_connection()
    try:
        count = run(connection)
        print(f"Updated assigned_to on {count} work item(s).")
    finally:
        connection.close()
```

Note: `raw_json` is stored as `JSONB`, so `psycopg` returns it already deserialized as a Python `dict` from the cursor — `json.dumps(raw_json)` re-serializes it back to a string so `extract_display_name` (which takes a JSON string, matching how it's tested and how `ado_client.py`'s `raw_json` is produced) can `json.loads` it uniformly.

- [ ] **Step 5: Run the unit tests to verify they pass**

Run: `cd apps/sync-service && python -m pytest tests/test_backfill_assigned_to_display_name.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Manually verify against the local Postgres test DB**

Run:
```bash
cd apps/sync-service
set TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/azure_sync_test
python -c "
import os, psycopg
from scripts.backfill_assigned_to_display_name import run
conn = psycopg.connect(os.environ['TEST_DATABASE_URL'])
with conn.cursor() as cur:
    cur.execute(\"INSERT INTO area_paths (organization, project, area_path) VALUES ('org','proj','proj\\\\A') RETURNING id\")
    ap = cur.fetchone()[0]
    cur.execute(
        \"INSERT INTO work_items (id, area_path_id, title, work_item_type, state, assigned_to, changed_date, raw_json) VALUES (999, %s, 'T', 'Bug', 'Active', 'alice@example.com', '2026-01-01', %s)\",
        (ap, '{\"fields\": {\"System.AssignedTo\": {\"displayName\": \"Alice\", \"uniqueName\": \"alice@example.com\"}}}'),
    )
conn.commit()
print('updated:', run(conn))
with conn.cursor() as cur:
    cur.execute('SELECT assigned_to FROM work_items WHERE id = 999')
    print('assigned_to now:', cur.fetchone()[0])
conn.rollback()
conn.close()
"
```
Expected output: `updated: 1` then `assigned_to now: Alice`

- [ ] **Step 7: Commit**

```bash
git add apps/sync-service/scripts/ apps/sync-service/tests/test_backfill_assigned_to_display_name.py
git commit -m "feat(sync-service): add one-off backfill script for Assigned To display names"
```

---

### Task 3: api-read — require `area_path_id` and add `search` in `repository.list_work_items`

**Files:**
- Modify: `apps/api-read/app/repository.py:28-75` (`list_work_items`)
- Test: `apps/api-read/tests/test_repository.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `list_work_items(conn, *, area_path_id: int, work_item_type: str | None = None [REMOVED — see below], search: str | None = None, page: int = 1, page_size: int = 50, order_by: str = "changed_date", order_dir: str = "desc") -> tuple[list[dict], int]`. `area_path_id` is now a required keyword arg (no default) that raises `repo.InvalidQueryParam` when `None`. The `work_item_type` parameter is removed entirely — Task 5 (routes) and Task 7 (frontend client) must not pass it.

- [ ] **Step 1: Write the failing tests**

Add to `apps/api-read/tests/test_repository.py` (below the existing tests, keep the existing `_seed_area_path`/`_seed_work_item` helpers as-is):

```python
def test_list_work_items_requires_area_path_id(db_conn):
    import pytest
    from app.repository import InvalidQueryParam

    with pytest.raises(InvalidQueryParam):
        repo.list_work_items(db_conn, area_path_id=None)


def test_list_work_items_search_matches_title(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_work_item(db_conn, ap1, 1, "Fix login bug", "Bug", "2026-01-01T00:00:00")
    _seed_work_item(db_conn, ap1, 2, "Add export button", "Task", "2026-01-02T00:00:00")

    rows, total = repo.list_work_items(db_conn, area_path_id=ap1, search="login")

    assert total == 1
    assert rows[0]["id"] == 1


def test_list_work_items_search_matches_id(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_work_item(db_conn, ap1, 42, "Item A", "Bug", "2026-01-01T00:00:00")
    _seed_work_item(db_conn, ap1, 43, "Item B", "Bug", "2026-01-02T00:00:00")

    rows, total = repo.list_work_items(db_conn, area_path_id=ap1, search="42")

    assert total == 1
    assert rows[0]["id"] == 42


def test_list_work_items_search_matches_work_item_type(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_work_item(db_conn, ap1, 1, "Item A", "Bug", "2026-01-01T00:00:00")
    _seed_work_item(db_conn, ap1, 2, "Item B", "Task", "2026-01-02T00:00:00")

    rows, total = repo.list_work_items(db_conn, area_path_id=ap1, search="task")

    assert total == 1
    assert rows[0]["id"] == 2


def test_list_work_items_search_matches_state(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_work_item(db_conn, ap1, 1, "Item A", "Bug", "2026-01-01T00:00:00")
    with db_conn.cursor() as cur:
        cur.execute("UPDATE work_items SET state = 'Resolved' WHERE id = 1")
    db_conn.commit()

    rows, total = repo.list_work_items(db_conn, area_path_id=ap1, search="resolved")

    assert total == 1
    assert rows[0]["id"] == 1


def test_list_work_items_search_matches_assigned_to(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_work_item(db_conn, ap1, 1, "Item A", "Bug", "2026-01-01T00:00:00")
    with db_conn.cursor() as cur:
        cur.execute("UPDATE work_items SET assigned_to = 'Alice' WHERE id = 1")
    db_conn.commit()

    rows, total = repo.list_work_items(db_conn, area_path_id=ap1, search="alice")

    assert total == 1
    assert rows[0]["id"] == 1


def test_list_work_items_search_combines_with_area_path_filter(db_conn):
    ap1 = _seed_area_path(db_conn, area_path="proj\\A")
    ap2 = _seed_area_path(db_conn, area_path="proj\\B")
    _seed_work_item(db_conn, ap1, 1, "Shared title", "Bug", "2026-01-01T00:00:00")
    _seed_work_item(db_conn, ap2, 2, "Shared title", "Bug", "2026-01-01T00:00:00")

    rows, total = repo.list_work_items(db_conn, area_path_id=ap1, search="Shared")

    assert total == 1
    assert rows[0]["id"] == 1


def test_list_work_items_empty_search_returns_all(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_work_item(db_conn, ap1, 1, "Item A", "Bug", "2026-01-01T00:00:00")

    rows, total = repo.list_work_items(db_conn, area_path_id=ap1, search="")

    assert total == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/api-read && python -m pytest tests/test_repository.py -v`
Expected: FAIL — `test_list_work_items_requires_area_path_id` fails because `area_path_id=None` currently returns all rows instead of raising; the `search=` tests fail with `TypeError: list_work_items() got an unexpected keyword argument 'search'`.

- [ ] **Step 3: Implement `area_path_id` requirement and `search` in `repository.py`**

Replace the full `list_work_items` function in `apps/api-read/app/repository.py` with:

```python
def list_work_items(
    conn: psycopg.Connection,
    *,
    area_path_id: int | None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
    order_by: str = "changed_date",
    order_dir: str = "desc",
) -> tuple[list[dict], int]:
    if area_path_id is None:
        raise InvalidQueryParam("area_path_id is required")
    if order_by not in _ORDER_BY_COLUMNS:
        raise InvalidQueryParam(f"invalid order_by: {order_by}")
    if order_dir not in _ORDER_DIRS:
        raise InvalidQueryParam(f"invalid order_dir: {order_dir}")
    if page < 1:
        raise InvalidQueryParam("page must be >= 1")
    if page_size < 1 or page_size > 200:
        raise InvalidQueryParam("page_size must be between 1 and 200")

    where_clauses = ["area_path_id = %s"]
    params: list = [area_path_id]

    search = (search or "").strip()
    if search:
        pattern = f"%{search}%"
        where_clauses.append(
            "(id::text ILIKE %s OR title ILIKE %s OR work_item_type ILIKE %s "
            "OR state ILIKE %s OR assigned_to ILIKE %s)"
        )
        params.extend([pattern, pattern, pattern, pattern, pattern])

    where_sql = f"WHERE {' AND '.join(where_clauses)}"

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT COUNT(*) AS total FROM work_items {where_sql}", params)
        total = cur.fetchone()["total"]

        offset = (page - 1) * page_size
        cur.execute(
            f"""
            SELECT id, area_path_id, title, work_item_type, state, assigned_to,
                   changed_date, parent_id
            FROM work_items
            {where_sql}
            ORDER BY {order_by} {order_dir}
            LIMIT %s OFFSET %s
            """,
            params + [page_size, offset],
        )
        rows = cur.fetchall()

    return rows, total
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/api-read && python -m pytest tests/test_repository.py -v`
Expected: PASS (all tests, including the pre-existing ones — note `test_list_work_items_filters_by_area_path_id` and the other pre-existing tests already pass `area_path_id=` explicitly, so they're unaffected by the new required arg)

- [ ] **Step 5: Run the readonly guardrail test to confirm no write SQL was introduced**

Run: `cd apps/api-read && python -m pytest tests/test_readonly_guardrail.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/api-read/app/repository.py apps/api-read/tests/test_repository.py
git commit -m "feat(api-read): require area_path_id and add unified search to list_work_items"
```

---

### Task 4: api-read — wire `search` through routes, drop `work_item_type`, surface 400 on missing area path

**Files:**
- Modify: `apps/api-read/app/routes.py:28-56` (`list_work_items` route)
- Test: `apps/api-read/tests/test_routes.py`

**Interfaces:**
- Consumes: `repo.list_work_items(conn, *, area_path_id, search=None, page=1, page_size=50, order_by="changed_date", order_dir="desc")` from Task 3.
- Produces: `GET /api/work-items` now returns 400 with `{"error": "area_path_id is required"}` when `area_path_id` is missing/absent, accepts `?search=...`, and no longer accepts/uses `?work_item_type=...`.

- [ ] **Step 1: Write the failing tests**

Add to `apps/api-read/tests/test_routes.py`:

```python
def test_list_work_items_requires_area_path_id(client, db_conn):
    response = client.get("/api/work-items")

    assert response.status_code == 400
    assert response.get_json() == {"error": "area_path_id is required"}


def test_list_work_items_search_param(client, db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s) RETURNING id",
            ("org", "proj", "proj\\A"),
        )
        area_path_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO work_items (id, area_path_id, title, work_item_type, state, changed_date, raw_json) VALUES (1, %s, 'Login bug', 'Bug', 'Active', '2026-01-01T00:00:00', '{}')",
            (area_path_id,),
        )
        cur.execute(
            "INSERT INTO work_items (id, area_path_id, title, work_item_type, state, changed_date, raw_json) VALUES (2, %s, 'Export feature', 'Task', 'Active', '2026-01-01T00:00:00', '{}')",
            (area_path_id,),
        )
    db_conn.commit()

    response = client.get(f"/api/work-items?area_path_id={area_path_id}&search=login")

    body = response.get_json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["id"] == 1
```

Also update the two existing tests that currently call `/api/work-items` without `area_path_id`:
- `test_list_work_items_default_envelope` (line 49): change the request to include the seeded area path id. After the existing seed block, capture the id and update the request line:

```python
def test_list_work_items_default_envelope(client, db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s) RETURNING id",
            ("org", "proj", "proj\\A"),
        )
        area_path_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO work_items (id, area_path_id, title, work_item_type, state, changed_date, raw_json)
            VALUES (1, %s, 'Item 1', 'Bug', 'Active', '2026-01-01T00:00:00', '{}')
            """,
            (area_path_id,),
        )
    db_conn.commit()

    response = client.get(f"/api/work-items?area_path_id={area_path_id}")

    assert response.status_code == 200
    body = response.get_json()
    assert body["pagination"] == {"page": 1, "page_size": 50, "total": 1}
    assert body["data"][0]["id"] == 1
```

- `test_list_work_items_rejects_invalid_order_by` (line 73): it currently hits `/api/work-items?order_by=raw_json` with no `area_path_id` — since `area_path_id` is checked first in Task 3's implementation, this would now 400 for the wrong reason. Update it to include a valid `area_path_id` so it still tests the `order_by` validation specifically:

```python
def test_list_work_items_rejects_invalid_order_by(client, db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s) RETURNING id",
            ("org", "proj", "proj\\A"),
        )
        area_path_id = cur.fetchone()[0]
    db_conn.commit()

    response = client.get(f"/api/work-items?area_path_id={area_path_id}&order_by=raw_json")

    assert response.status_code == 400
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/api-read && python -m pytest tests/test_routes.py -v`
Expected: FAIL — the new `test_list_work_items_requires_area_path_id` fails because the route currently returns 200 with all rows; `test_list_work_items_search_param` fails with a 200 that includes both rows (search isn't wired yet).

- [ ] **Step 3: Update the route**

Replace the `list_work_items` route body in `apps/api-read/app/routes.py`:

```python
    @app.route("/api/work-items", methods=["GET"])
    def list_work_items():
        conn = conn_factory()
        try:
            area_path_id = request.args.get("area_path_id", type=int)
            search = request.args.get("search")
            page = request.args.get("page", default=1, type=int)
            page_size = request.args.get("page_size", default=50, type=int)
            order_by = request.args.get("order_by", default="changed_date")
            order_dir = request.args.get("order_dir", default="desc")

            rows, total = repo.list_work_items(
                conn,
                area_path_id=area_path_id,
                search=search,
                page=page,
                page_size=page_size,
                order_by=order_by,
                order_dir=order_dir,
            )
        except repo.InvalidQueryParam as exc:
            return jsonify({"error": str(exc)}), 400

        return jsonify(
            {
                "data": rows,
                "pagination": {"page": page, "page_size": page_size, "total": total},
            }
        )
```

(This removes the `work_item_type = request.args.get("work_item_type")` line and its pass-through, and adds `search`.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/api-read && python -m pytest tests/test_routes.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Run the full api-read test suite**

Run: `cd apps/api-read && python -m pytest -v`
Expected: PASS (all tests across `test_repository.py`, `test_routes.py`, `test_readonly_guardrail.py`)

- [ ] **Step 6: Commit**

```bash
git add apps/api-read/app/routes.py apps/api-read/tests/test_routes.py
git commit -m "feat(api-read): require area_path_id and wire search param in /api/work-items"
```

---

### Task 5: web-read — update API client for `search`, drop `workItemType`

**Files:**
- Modify: `apps/web-read/src/services/apiReadClient.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `WorkItemListParams` with fields `{ areaPathId?: number; search?: string; page?: number; pageSize?: number; orderBy?: "changed_date" | "id" | "title"; orderDir?: "asc" | "desc" }` (removed `workItemType`, added `search`). `fetchWorkItems(params: WorkItemListParams): Promise<PaginatedResponse<WorkItem>>` unchanged signature, just sends `search` instead of `work_item_type` in the query string. Task 6 depends on this exact param shape.

There's no dedicated test file for this client (it's a thin fetch wrapper exercised via the page component); Task 6's manual browser verification covers it end-to-end. Make the change directly:

- [ ] **Step 1: Update `WorkItemListParams` and `fetchWorkItems`**

In `apps/web-read/src/services/apiReadClient.ts`, replace:

```typescript
export interface WorkItemListParams {
  areaPathId?: number;
  workItemType?: string;
  page?: number;
  pageSize?: number;
  orderBy?: "changed_date" | "id" | "title";
  orderDir?: "asc" | "desc";
}

export async function fetchWorkItems(
  params: WorkItemListParams = {}
): Promise<PaginatedResponse<WorkItem>> {
  const query = new URLSearchParams();
  if (params.areaPathId !== undefined) query.set("area_path_id", String(params.areaPathId));
  if (params.workItemType) query.set("work_item_type", params.workItemType);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.pageSize ?? 50));
  query.set("order_by", params.orderBy ?? "changed_date");
  query.set("order_dir", params.orderDir ?? "desc");

  const response = await fetch(`${BASE_URL}/api/work-items?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch work items: ${response.status}`);
  }
  return response.json();
}
```

with:

```typescript
export interface WorkItemListParams {
  areaPathId?: number;
  search?: string;
  page?: number;
  pageSize?: number;
  orderBy?: "changed_date" | "id" | "title";
  orderDir?: "asc" | "desc";
}

export async function fetchWorkItems(
  params: WorkItemListParams = {}
): Promise<PaginatedResponse<WorkItem>> {
  const query = new URLSearchParams();
  if (params.areaPathId !== undefined) query.set("area_path_id", String(params.areaPathId));
  if (params.search) query.set("search", params.search);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.pageSize ?? 50));
  query.set("order_by", params.orderBy ?? "changed_date");
  query.set("order_dir", params.orderDir ?? "desc");

  const response = await fetch(`${BASE_URL}/api/work-items?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch work items: ${response.status}`);
  }
  return response.json();
}
```

- [ ] **Step 2: Type-check the project**

Run: `cd apps/web-read && npx tsc --noEmit`
Expected: no errors yet — `WorkItemsListPage.tsx` still references `workItemType`/`setWorkItemType`, so this will actually FAIL right now with `Property 'workItemType' does not exist on type 'WorkItemListParams'`. That's expected — Task 6 fixes the page. Do not attempt to fix it in this task.

- [ ] **Step 3: Commit**

```bash
git add apps/web-read/src/services/apiReadClient.ts
git commit -m "feat(web-read): switch apiReadClient from workItemType to search param"
```

---

### Task 6: web-read — required area path (auto-select first), single search field, drop Type filter

**Files:**
- Modify: `apps/web-read/src/pages/WorkItemsListPage.tsx`

**Interfaces:**
- Consumes: `fetchAreaPaths(): Promise<AreaPath[]>`, `fetchWorkItems(params: WorkItemListParams): Promise<PaginatedResponse<WorkItem>>` and `WorkItemListParams` from Task 5 (now has `search?: string`, no `workItemType`).
- Produces: the page component only — nothing downstream depends on its internals.

- [ ] **Step 1: Replace the component body**

Replace the full contents of `apps/web-read/src/pages/WorkItemsListPage.tsx` with:

```typescript
import { useEffect, useState } from "react";
import { Card } from "@astryxdesign/core/Layout";
import { HStack } from "@astryxdesign/core/Layout";
import { Selector } from "@astryxdesign/core/Selector";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Table, proportional, pixel } from "@astryxdesign/core/Table";
import { Pagination } from "@astryxdesign/core/Pagination";
import { Banner } from "@astryxdesign/core/Banner";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Badge } from "@astryxdesign/core/Badge";
import { fetchWorkItems, fetchAreaPaths } from "../services/apiReadClient";
import type { WorkItem } from "../models/workItem";
import type { AreaPath } from "../models/areaPath";

type WorkItemRow = WorkItem & Record<string, unknown>;

const PAGE_SIZE = 50;

export default function WorkItemsListPage() {
  const [areaPaths, setAreaPaths] = useState<AreaPath[]>([]);
  const [areaPathsLoaded, setAreaPathsLoaded] = useState(false);
  const [items, setItems] = useState<WorkItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [areaPathId, setAreaPathId] = useState<number | undefined>(undefined);
  const [search, setSearch] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAreaPaths()
      .then((paths) => {
        setAreaPaths(paths);
        if (paths.length > 0) {
          setAreaPathId(paths[0].id);
        }
      })
      .catch(() => {
        /* handled below via areaPathsLoaded + empty areaPaths */
      })
      .finally(() => setAreaPathsLoaded(true));
  }, []);

  useEffect(() => {
    if (areaPathId === undefined) {
      return;
    }
    setLoading(true);
    setError(null);
    fetchWorkItems({
      areaPathId,
      search: search || undefined,
      page,
      pageSize: PAGE_SIZE,
    })
      .then((response) => {
        setItems(response.data);
        setTotal(response.pagination.total);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [areaPathId, search, page]);

  return (
    <Card>
      <HStack gap={4} align="end" wrap="wrap">
        <Selector
          label="Area path"
          hasSearch
          value={areaPathId !== undefined ? String(areaPathId) : null}
          onChange={(value) => {
            setPage(1);
            setAreaPathId(value ? Number(value) : undefined);
          }}
          options={areaPaths.map((ap) => ({
            value: String(ap.id),
            label: ap.area_path,
          }))}
          width={280}
        />
        <TextInput
          label="Search"
          hasClear
          value={search}
          onChange={(value) => {
            setPage(1);
            setSearch(value);
          }}
          placeholder="Search by id, title, type, state, assigned to"
          width={320}
        />
      </HStack>

      {error && (
        <Banner status="error" title="Error loading work items" description={error} />
      )}

      {areaPathsLoaded && areaPaths.length === 0 && (
        <EmptyState
          title="No area paths configured"
          description="Configure at least one area path in the sync service to see work items."
        />
      )}

      {areaPathId !== undefined && loading && !error && (
        <Spinner label="Loading work items" />
      )}

      {areaPathId !== undefined && !loading && !error && items.length === 0 && (
        <EmptyState
          title="No work items found"
          description="Try adjusting the search."
        />
      )}

      {areaPathId !== undefined && !loading && !error && items.length > 0 && (
        <>
          <Table
            data={items as WorkItemRow[]}
            idKey="id"
            density="balanced"
            dividers="rows"
            hasHover
            columns={[
              { key: "id", header: "ID", width: pixel(80) },
              { key: "title", header: "Title", width: proportional(3) },
              { key: "work_item_type", header: "Type", width: proportional(1) },
              {
                key: "state",
                header: "State",
                width: proportional(1),
                renderCell: (item: WorkItemRow) => (
                  <Badge label={item.state ?? "—"} />
                ),
              },
              { key: "assigned_to", header: "Assigned To", width: proportional(1) },
              { key: "changed_date", header: "Changed Date", width: proportional(1) },
            ]}
          />

          <Pagination
            variant="compact"
            page={page}
            onChange={setPage}
            totalItems={total}
            pageSize={PAGE_SIZE}
          />
        </>
      )}
    </Card>
  );
}
```

Key behavior changes from the previous version:
- `areaPathId` is set to `areaPaths[0].id` as soon as area paths load (never left as "All"/`undefined` when at least one exists).
- The Area Path `Selector` dropped `hasClear` and the `placeholder="All"` — there's no valid "unset" state once area paths have loaded.
- The `TextInput label="Type"` is gone; a single `TextInput label="Search"` replaces it and feeds `search` into `fetchWorkItems`.
- The work-items fetch effect returns early (no fetch, no spinner) while `areaPathId` is still `undefined` (i.e., before area paths have loaded, or if there are none) — the `EmptyState` for "No area paths configured" covers that case instead.

- [ ] **Step 2: Type-check the project**

Run: `cd apps/web-read && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 3: Manually verify in the browser**

Run the backend and frontend:
```bash
cd apps/api-read && set DATABASE_URL=<your local Postgres URL> && python -c "from app import db; db.init_schema(db.get_connection())"
cd apps/api-read && flask --app app.routes:create_app run --port 5001
```
(in a second terminal)
```bash
cd apps/web-read && npm run dev
```

Open the app in a browser (default Vite port, typically `http://127.0.0.1:5173`) and confirm:
- If at least one area path exists in the DB, the Area Path selector shows the first one pre-selected on load, and work items for it load immediately without any manual selection.
- Typing in the Search field (e.g. part of a title, an id, a state name, or an assignee's name) narrows the table to matching rows, and clearing it restores the full list for that area path.
- Changing the Area Path selector re-runs the search with the new area path and resets to page 1.
- The Assigned To column shows names (e.g. "Alice"), not email addresses, for any work item whose `raw_json` was written after Task 1's fix (or backfilled via Task 2's script).

- [ ] **Step 4: Commit**

```bash
git add apps/web-read/src/pages/WorkItemsListPage.tsx
git commit -m "feat(web-read): require area path selection, add unified search, drop Type filter"
```

---

## Self-Review Notes

- Spec coverage: display-name Assigned To (Task 1 + 2), area path required + auto-select first (Task 6), unified search over ID/Title/Type/State/Assigned To (Tasks 3, 4, 6), search applied server-side (Task 3), Type filter removed (Task 6), `/api/work-items` requires `area_path_id` (Tasks 3, 4) — all requirements from the spec have a task.
- No placeholders: every step has literal code or an exact command with expected output.
- Type/name consistency checked: `search` (not `q` or `query`) is used consistently in `repository.py`, `routes.py`, `apiReadClient.ts`, and `WorkItemsListPage.tsx`; `area_path_id` (snake_case in Python/query-string, `areaPathId` in TypeScript) matches the existing convention already used for that field pre-change.
