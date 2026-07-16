# Features Roadmap (tree + Gantt) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new page that lists Features in a tree under their parent (Epic or Solution, with roll-up start/target dates) and renders the same data as a monthly Gantt, both built entirely from Astryx components.

**Architecture:** Backfill two new columns (`start_date`, `target_date`) onto `work_items` in `apps/sync-service`, expose them through a new flat `/api/features-tree` endpoint in `apps/api-read`, and assemble the tree + Gantt client-side in `apps/web-read` (`FeaturesRoadmapPage.tsx`) using `TreeList` and `Table`.

**Tech Stack:** Python/Flask/psycopg (`apps/sync-service`, `apps/api-read`), React/TypeScript/Vite + `@astryxdesign/core` (`apps/web-read`). No new runtime dependency except `vitest` (dev-only) to unit-test the new pure TS tree/Gantt logic.

## Global Constraints

- UI must use only `@astryxdesign/core` components — no styled-components, emotion, inline `style=`, or custom CSS/stylesheets (project `CLAUDE.md` rule).
- `apps/api-read/app/repository.py` must contain only `SELECT` statements — `apps/sync-service` is the only writer (`docs/adr/0002-single-writer.md`, enforced by `apps/api-read/tests/test_readonly_guardrail.py`).
- `apps/sync-service` writes are idempotent upserts — no separate backfill migration script; the next scheduled sync repopulates new columns for existing rows.
- New DB columns are added via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` inside `SCHEMA_SQL` in `apps/sync-service/app/db.py`, matching the existing `parent_id` pattern — no separate migration files.
- Gantt resolution is monthly only; a Feature is included in the Gantt only if it has both `start_date` and `target_date`; the tree page still shows Features missing one/both dates (as `—`).

---

### Task 1: Backfill `start_date`/`target_date` columns and extraction in apps/sync-service

**Files:**
- Modify: `apps/sync-service/app/db.py` (add two `ALTER TABLE` lines to `SCHEMA_SQL`)
- Modify: `apps/sync-service/app/ado_client.py:128-160` (`_map_work_item`)
- Modify: `apps/sync-service/app/repository.py:118-152` (`upsert_work_items`)
- Test: `apps/sync-service/tests/test_ado_client.py`
- Test: `apps/sync-service/tests/test_db.py`
- Test: `apps/sync-service/tests/test_repository.py`

**Interfaces:**
- Consumes: nothing new — extends the existing `_map_work_item(raw: dict) -> dict` and `upsert_work_items(conn, area_path_id, items: list[dict]) -> None`.
- Produces: `work_items.start_date` / `work_items.target_date` (nullable `TIMESTAMP` columns); `_map_work_item` output dicts now include `"start_date"` and `"target_date"` keys (both `datetime.datetime | None`); these are consumed by Task 4's `list_features_tree`.

- [ ] **Step 1: Write the failing test for `_map_work_item` date extraction**

Add to `apps/sync-service/tests/test_ado_client.py` (same file/pattern as the existing `test_get_work_items_batch...` test around line 60-98):

```python
@patch("app.ado_client.requests.post")
def test_get_work_items_batch_extracts_start_and_target_dates(mock_post):
    mock_post.return_value = _response(
        200,
        {
            "value": [
                {
                    "id": 1,
                    "fields": {
                        "System.Title": "Feature A",
                        "System.WorkItemType": "Feature",
                        "System.State": "Active",
                        "System.ChangedDate": "2026-07-01T12:00:00Z",
                        "Microsoft.VSTS.Scheduling.StartDate": "2026-01-10T00:00:00Z",
                        "Microsoft.VSTS.Scheduling.TargetDate": "2026-02-28T00:00:00Z",
                    },
                }
            ]
        },
    )

    client = AdoClient("org", "proj", pat="fake-pat")
    items = client.get_work_items_batch([1])

    item = items[0]
    assert item["start_date"] == datetime.datetime(2026, 1, 10, 0, 0, 0)
    assert item["target_date"] == datetime.datetime(2026, 2, 28, 0, 0, 0)


@patch("app.ado_client.requests.post")
def test_get_work_items_batch_handles_missing_scheduling_dates(mock_post):
    mock_post.return_value = _response(
        200,
        {
            "value": [
                {
                    "id": 2,
                    "fields": {
                        "System.Title": "Bug B",
                        "System.WorkItemType": "Bug",
                        "System.State": "Active",
                        "System.ChangedDate": "2026-07-01T12:00:00Z",
                    },
                }
            ]
        },
    )

    client = AdoClient("org", "proj", pat="fake-pat")
    items = client.get_work_items_batch([2])

    item = items[0]
    assert item["start_date"] is None
    assert item["target_date"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/sync-service && pytest tests/test_ado_client.py -k "start_and_target_dates or missing_scheduling_dates" -v`
Expected: FAIL with `KeyError: 'start_date'`

- [ ] **Step 3: Implement date extraction in `_map_work_item`**

In `apps/sync-service/app/ado_client.py`, factor out the existing inline `changed_date` parsing into a small helper and reuse it for the two new fields. Replace the body of `_map_work_item` (lines ~128-160) with:

```python
    @staticmethod
    def _parse_ado_date(raw_value: str | None) -> datetime.datetime | None:
        if not raw_value:
            return None
        return datetime.datetime.strptime(
            raw_value.split(".")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S"
        )

    @staticmethod
    def _map_work_item(raw: dict) -> dict:
        fields = raw.get("fields", {})
        assigned_to_field = fields.get("System.AssignedTo")
        assigned_to = None
        if isinstance(assigned_to_field, dict):
            assigned_to = assigned_to_field.get("displayName")
        elif isinstance(assigned_to_field, str):
            assigned_to = assigned_to_field

        changed_date = AdoClient._parse_ado_date(fields.get("System.ChangedDate"))
        start_date = AdoClient._parse_ado_date(
            fields.get("Microsoft.VSTS.Scheduling.StartDate")
        )
        target_date = AdoClient._parse_ado_date(
            fields.get("Microsoft.VSTS.Scheduling.TargetDate")
        )

        parent_id = fields.get("System.Parent")
        if parent_id is None:
            for relation in raw.get("relations", []):
                if relation.get("rel") == "System.LinkTypes.Hierarchy-Reverse":
                    parent_id = int(relation["url"].rsplit("/", 1)[-1])
                    break

        return {
            "id": raw["id"],
            "title": fields.get("System.Title"),
            "work_item_type": fields.get("System.WorkItemType"),
            "state": fields.get("System.State"),
            "assigned_to": assigned_to,
            "changed_date": changed_date,
            "start_date": start_date,
            "target_date": target_date,
            "parent_id": parent_id,
            "raw_json": json.dumps(raw),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/sync-service && pytest tests/test_ado_client.py -v`
Expected: PASS (all tests in the file, including the two new ones and the pre-existing `test_get_work_items_batch...`)

- [ ] **Step 5: Write the failing test for the schema columns**

Add to `apps/sync-service/tests/test_db.py` (check the file first for its existing pattern of asserting columns via `information_schema.columns`; follow that same style). If no such helper exists yet, add:

```python
def test_work_items_has_start_and_target_date_columns(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'work_items' AND column_name IN ('start_date', 'target_date')
            """
        )
        columns = {row[0] for row in cur.fetchall()}
    assert columns == {"start_date", "target_date"}
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd apps/sync-service && pytest tests/test_db.py -k start_and_target_date -v`
Expected: FAIL — `columns == set()`, not `{"start_date", "target_date"}`

- [ ] **Step 7: Add the columns to `SCHEMA_SQL`**

In `apps/sync-service/app/db.py`, immediately after the existing line:

```python
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS parent_id INTEGER;
```

add:

```python
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS start_date TIMESTAMP;
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS target_date TIMESTAMP;
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd apps/sync-service && pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 9: Write the failing test for `upsert_work_items` persisting the new columns**

Add to `apps/sync-service/tests/test_repository.py` (find the existing `upsert_work_items` test(s) and follow that seeding pattern — it seeds an `area_path`, calls `repo.upsert_work_items`, then reads back via a direct `SELECT`):

```python
def test_upsert_work_items_persists_start_and_target_date(db_conn):
    area_path_id = _seed_area_path(db_conn)  # reuse this file's existing helper name
    repo.upsert_work_items(
        db_conn,
        area_path_id,
        [
            {
                "id": 1,
                "title": "Feature A",
                "work_item_type": "Feature",
                "state": "Active",
                "assigned_to": None,
                "changed_date": datetime.datetime(2026, 7, 1, 12, 0, 0),
                "start_date": datetime.datetime(2026, 1, 10, 0, 0, 0),
                "target_date": datetime.datetime(2026, 2, 28, 0, 0, 0),
                "parent_id": None,
                "raw_json": "{}",
            }
        ],
    )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT start_date, target_date FROM work_items WHERE id = 1")
        start_date, target_date = cur.fetchone()

    assert start_date == datetime.datetime(2026, 1, 10, 0, 0, 0)
    assert target_date == datetime.datetime(2026, 2, 28, 0, 0, 0)
```

Check the top of `test_repository.py` for the exact existing helper name that seeds an area path (e.g. `_seed_area_path`) and reuse it verbatim instead of redefining it; add `import datetime` at the top of the file if not already present.

- [ ] **Step 10: Run test to verify it fails**

Run: `cd apps/sync-service && pytest tests/test_repository.py -k start_and_target_date -v`
Expected: FAIL with a `KeyError: 'start_date'` raised from inside `upsert_work_items`

- [ ] **Step 11: Implement in `upsert_work_items`**

Replace the `INSERT INTO work_items ...` statement in `apps/sync-service/app/repository.py` (lines ~121-149) with:

```python
            cur.execute(
                """
                INSERT INTO work_items
                    (id, area_path_id, title, work_item_type, state, assigned_to, changed_date,
                     start_date, target_date, parent_id, raw_json, synced_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (id) DO UPDATE SET
                    area_path_id = EXCLUDED.area_path_id,
                    title = EXCLUDED.title,
                    work_item_type = EXCLUDED.work_item_type,
                    state = EXCLUDED.state,
                    assigned_to = EXCLUDED.assigned_to,
                    changed_date = EXCLUDED.changed_date,
                    start_date = EXCLUDED.start_date,
                    target_date = EXCLUDED.target_date,
                    parent_id = EXCLUDED.parent_id,
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
                    item.get("start_date"),
                    item.get("target_date"),
                    item.get("parent_id"),
                    item["raw_json"],
                ),
            )
```

- [ ] **Step 12: Run test to verify it passes**

Run: `cd apps/sync-service && pytest tests/test_repository.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 13: Run the full sync-service test suite**

Run: `cd apps/sync-service && pytest -v`
Expected: PASS (all tests, including `test_sync_service.py` — `upsert_work_items` is called from `sync_service.run_sync` with dicts produced by `_map_work_item`, so the added keys must not break that flow)

- [ ] **Step 14: Commit**

```bash
cd apps/sync-service
git add app/db.py app/ado_client.py app/repository.py tests/test_ado_client.py tests/test_db.py tests/test_repository.py
git commit -m "feat(sync-service): sync start_date and target_date from ADO scheduling fields"
```

---

### Task 2: `list_features_tree` read query in apps/api-read

**Files:**
- Modify: `apps/api-read/app/repository.py`
- Test: `apps/api-read/tests/test_repository.py`

**Interfaces:**
- Consumes: `work_items` columns from Task 1 (`start_date`, `target_date`, plus existing `parent_id`, `work_item_type`).
- Produces: `list_features_tree(conn: psycopg.Connection, *, area_path_id: int) -> list[dict]`, each dict shaped `{"id": int, "title": str | None, "work_item_type": str | None, "parent_id": int | None, "start_date": datetime | None, "target_date": datetime | None}`, ordered by `id`. Consumed by Task 3's route handler.

- [ ] **Step 1: Write the failing test**

Add to `apps/api-read/tests/test_repository.py` (reuse this file's existing `_seed_area_path` helper; check its exact seeding-for-work-item pattern too — likely a raw `INSERT INTO work_items` via `db_conn.cursor()`, matching `test_list_work_items_filters_by_area_path_id`):

```python
def _seed_feature_tree_item(
    conn, area_path_id, item_id, title, work_item_type, parent_id=None,
    start_date=None, target_date=None,
):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO work_items
                (id, area_path_id, title, work_item_type, state, parent_id,
                 start_date, target_date, raw_json)
            VALUES (%s, %s, %s, %s, 'Active', %s, %s, %s, '{}')
            """,
            (item_id, area_path_id, title, work_item_type, parent_id, start_date, target_date),
        )
    conn.commit()


def test_list_features_tree_returns_only_feature_epic_solution(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_feature_tree_item(db_conn, ap1, 1, "Sol A", "Solution")
    _seed_feature_tree_item(db_conn, ap1, 2, "Epic A", "Epic", parent_id=1)
    _seed_feature_tree_item(db_conn, ap1, 3, "Feat A", "Feature", parent_id=2)
    _seed_feature_tree_item(db_conn, ap1, 4, "Bug A", "Bug", parent_id=2)

    rows = repo.list_features_tree(db_conn, area_path_id=ap1)

    assert [r["id"] for r in rows] == [1, 2, 3]


def test_list_features_tree_filters_by_area_path_id(db_conn):
    ap1 = _seed_area_path(db_conn, area_path="proj\\A")
    ap2 = _seed_area_path(db_conn, area_path="proj\\B")
    _seed_feature_tree_item(db_conn, ap1, 1, "Feat A", "Feature")
    _seed_feature_tree_item(db_conn, ap2, 2, "Feat B", "Feature")

    rows = repo.list_features_tree(db_conn, area_path_id=ap1)

    assert [r["id"] for r in rows] == [1]


def test_list_features_tree_includes_dates_and_parent(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_feature_tree_item(
        db_conn, ap1, 1, "Feat A", "Feature", parent_id=None,
        start_date="2026-01-10T00:00:00", target_date="2026-02-28T00:00:00",
    )

    rows = repo.list_features_tree(db_conn, area_path_id=ap1)

    assert rows[0]["parent_id"] is None
    assert rows[0]["start_date"].isoformat() == "2026-01-10T00:00:00"
    assert rows[0]["target_date"].isoformat() == "2026-02-28T00:00:00"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api-read && pytest tests/test_repository.py -k list_features_tree -v`
Expected: FAIL with `AttributeError: module 'app.repository' has no attribute 'list_features_tree'`

- [ ] **Step 3: Implement `list_features_tree`**

Add to `apps/api-read/app/repository.py`, after `list_work_items`:

```python
def list_features_tree(conn: psycopg.Connection, *, area_path_id: int) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, title, work_item_type, parent_id, start_date, target_date
            FROM work_items
            WHERE area_path_id = %s
              AND work_item_type IN ('Feature', 'Epic', 'Solution')
            ORDER BY id
            """,
            (area_path_id,),
        )
        return cur.fetchall()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api-read && pytest tests/test_repository.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Run the readonly guardrail test**

Run: `cd apps/api-read && pytest tests/test_readonly_guardrail.py -v`
Expected: PASS — confirms the new function still contains only a `SELECT`

- [ ] **Step 6: Commit**

```bash
cd apps/api-read
git add app/repository.py tests/test_repository.py
git commit -m "feat(api-read): add list_features_tree query for Feature/Epic/Solution rollup"
```

---

### Task 3: `GET /api/features-tree` route in apps/api-read

**Files:**
- Modify: `apps/api-read/app/routes.py`
- Test: `apps/api-read/tests/test_routes.py`

**Interfaces:**
- Consumes: `repo.list_features_tree(conn, *, area_path_id: int) -> list[dict]` from Task 2.
- Produces: `GET /api/features-tree?area_path_id=<id>` → `200 {"data": [...]}` on success, `400 {"error": "area_path_id is required"}` when the query param is missing. Consumed by Task 4's `fetchFeaturesTree`.

- [ ] **Step 1: Write the failing test**

Add to `apps/api-read/tests/test_routes.py`:

```python
def test_list_features_tree_returns_envelope(client, db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s) RETURNING id",
            ("org", "proj", "proj\\A"),
        )
        area_path_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO work_items (id, area_path_id, title, work_item_type, state, parent_id, start_date, target_date, raw_json)
            VALUES (1, %s, 'Feat A', 'Feature', 'Active', NULL, '2026-01-10T00:00:00', '2026-02-28T00:00:00', '{}')
            """,
            (area_path_id,),
        )
    db_conn.commit()

    response = client.get(f"/api/features-tree?area_path_id={area_path_id}")

    assert response.status_code == 200
    body = response.get_json()
    assert body["data"][0]["id"] == 1
    assert body["data"][0]["work_item_type"] == "Feature"
    assert body["data"][0]["start_date"] == "2026-01-10T00:00:00"
    assert body["data"][0]["target_date"] == "2026-02-28T00:00:00"


def test_list_features_tree_requires_area_path_id(client):
    response = client.get("/api/features-tree")

    assert response.status_code == 400
    assert response.get_json() == {"error": "area_path_id is required"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api-read && pytest tests/test_routes.py -k features_tree -v`
Expected: FAIL with 404 (route not found)

- [ ] **Step 3: Implement the route**

Add to `apps/api-read/app/routes.py`, after the `/api/work-items` route, inside `create_app`:

```python
    @app.route("/api/features-tree", methods=["GET"])
    def list_features_tree():
        area_path_id = request.args.get("area_path_id", type=int)
        if area_path_id is None:
            return jsonify({"error": "area_path_id is required"}), 400

        conn = conn_factory()
        rows = repo.list_features_tree(conn, area_path_id=area_path_id)
        return jsonify({"data": rows})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api-read && pytest tests/test_routes.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Run the full api-read test suite**

Run: `cd apps/api-read && pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd apps/api-read
git add app/routes.py tests/test_routes.py
git commit -m "feat(api-read): add GET /api/features-tree endpoint"
```

---

### Task 4: Frontend data layer — model, API client, tree builder, Gantt month builder

**Files:**
- Create: `apps/web-read/src/models/feature.ts`
- Modify: `apps/web-read/src/services/apiReadClient.ts`
- Create: `apps/web-read/src/utils/buildFeatureTree.ts`
- Create: `apps/web-read/src/utils/buildFeatureTree.test.ts`
- Create: `apps/web-read/src/utils/ganttMonths.ts`
- Create: `apps/web-read/src/utils/ganttMonths.test.ts`
- Modify: `apps/web-read/package.json`

**Interfaces:**
- Consumes: `GET /api/features-tree?area_path_id=<id>` from Task 3, returning `{"data": FeatureTreeItem[]}` (ISO date strings, not JS `Date` objects — matches how `changed_date` is already handled as a plain string in `models/workItem.ts`).
- Produces:
  - `FeatureTreeItem` (`models/feature.ts`): `{id: number; title: string | null; work_item_type: string | null; parent_id: number | null; start_date: string | null; target_date: string | null}`
  - `fetchFeaturesTree(areaPathId: number): Promise<FeatureTreeItem[]>` (`services/apiReadClient.ts`)
  - `FeatureTreeNode` (`utils/buildFeatureTree.ts`): `{id: number; title: string; workItemType: string; startDate: string | null; targetDate: string | null; children: FeatureTreeNode[]}`
  - `buildFeatureTree(items: FeatureTreeItem[]): FeatureTreeNode[]` (`utils/buildFeatureTree.ts`)
  - `GanttMonth` (`utils/ganttMonths.ts`): `{key: string; label: string}` (`key` is `"YYYY-MM"`)
  - `buildGanttMonths(items: FeatureTreeItem[]): GanttMonth[]` (`utils/ganttMonths.ts`)
  - `featureCoversMonth(item: FeatureTreeItem, monthKey: string): boolean` (`utils/ganttMonths.ts`)
  - All four are consumed by Task 5's `FeaturesRoadmapPage.tsx`.

- [ ] **Step 1: Add vitest to apps/web-read**

Run: `cd apps/web-read && npm install --save-dev vitest`

Edit `apps/web-read/package.json` `scripts` block to add a `test` entry (keep existing `dev`/`build`/`preview` entries as-is):

```json
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
```

- [ ] **Step 2: Create the model**

Create `apps/web-read/src/models/feature.ts`:

```ts
export interface FeatureTreeItem {
  id: number;
  title: string | null;
  work_item_type: string | null;
  parent_id: number | null;
  start_date: string | null;
  target_date: string | null;
}
```

- [ ] **Step 3: Add `fetchFeaturesTree` to the API client**

Add to `apps/web-read/src/services/apiReadClient.ts` (after `fetchAreaPaths`, and add `import type { FeatureTreeItem } from "../models/feature";` at the top alongside the other type imports):

```ts
export async function fetchFeaturesTree(areaPathId: number): Promise<FeatureTreeItem[]> {
  const response = await fetch(
    `${BASE_URL}/api/features-tree?area_path_id=${encodeURIComponent(String(areaPathId))}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch features tree: ${response.status}`);
  }
  const body = await response.json();
  return body.data;
}
```

- [ ] **Step 4: Write the failing test for `buildFeatureTree`**

Create `apps/web-read/src/utils/buildFeatureTree.test.ts`:

```ts
import { describe, expect, test } from "vitest";
import { buildFeatureTree } from "./buildFeatureTree";
import type { FeatureTreeItem } from "../models/feature";

function item(overrides: Partial<FeatureTreeItem>): FeatureTreeItem {
  return {
    id: 1,
    title: "Item",
    work_item_type: "Feature",
    parent_id: null,
    start_date: null,
    target_date: null,
    ...overrides,
  };
}

describe("buildFeatureTree", () => {
  test("nests Feature under Epic under Solution", () => {
    const tree = buildFeatureTree([
      item({ id: 1, title: "Sol A", work_item_type: "Solution", parent_id: null }),
      item({ id: 2, title: "Epic A", work_item_type: "Epic", parent_id: 1 }),
      item({ id: 3, title: "Feat A", work_item_type: "Feature", parent_id: 2 }),
    ]);

    expect(tree).toHaveLength(1);
    expect(tree[0].id).toBe(1);
    expect(tree[0].children).toHaveLength(1);
    expect(tree[0].children[0].id).toBe(2);
    expect(tree[0].children[0].children).toHaveLength(1);
    expect(tree[0].children[0].children[0].id).toBe(3);
  });

  test("nests Feature directly under Solution when it has no Epic parent", () => {
    const tree = buildFeatureTree([
      item({ id: 1, title: "Sol A", work_item_type: "Solution", parent_id: null }),
      item({ id: 2, title: "Feat A", work_item_type: "Feature", parent_id: 1 }),
    ]);

    expect(tree[0].children).toHaveLength(1);
    expect(tree[0].children[0].id).toBe(2);
    expect(tree[0].children[0].children).toHaveLength(0);
  });

  test("rolls up start_date as the min and target_date as the max of descendants", () => {
    const tree = buildFeatureTree([
      item({ id: 1, title: "Epic A", work_item_type: "Epic", parent_id: null }),
      item({
        id: 2, title: "Feat A", work_item_type: "Feature", parent_id: 1,
        start_date: "2026-02-01T00:00:00", target_date: "2026-03-01T00:00:00",
      }),
      item({
        id: 3, title: "Feat B", work_item_type: "Feature", parent_id: 1,
        start_date: "2026-01-01T00:00:00", target_date: "2026-02-15T00:00:00",
      }),
    ]);

    expect(tree[0].startDate).toBe("2026-01-01T00:00:00");
    expect(tree[0].targetDate).toBe("2026-03-01T00:00:00");
  });

  test("a parent with no dated descendants has null roll-up dates", () => {
    const tree = buildFeatureTree([
      item({ id: 1, title: "Epic A", work_item_type: "Epic", parent_id: null }),
      item({ id: 2, title: "Feat A", work_item_type: "Feature", parent_id: 1 }),
    ]);

    expect(tree[0].startDate).toBeNull();
    expect(tree[0].targetDate).toBeNull();
  });

  test("falls back to '#id' label when title is null", () => {
    const tree = buildFeatureTree([
      item({ id: 1, title: null, work_item_type: "Solution", parent_id: null }),
    ]);

    expect(tree[0].title).toBe("#1");
  });
});
```

- [ ] **Step 5: Run test to verify it fails**

Run: `cd apps/web-read && npx vitest run src/utils/buildFeatureTree.test.ts`
Expected: FAIL — `Cannot find module './buildFeatureTree'`

- [ ] **Step 6: Implement `buildFeatureTree`**

Create `apps/web-read/src/utils/buildFeatureTree.ts`:

```ts
import type { FeatureTreeItem } from "../models/feature";

export interface FeatureTreeNode {
  id: number;
  title: string;
  workItemType: string;
  startDate: string | null;
  targetDate: string | null;
  children: FeatureTreeNode[];
}

function minDate(a: string | null, b: string | null): string | null {
  if (a === null) return b;
  if (b === null) return a;
  return a < b ? a : b;
}

function maxDate(a: string | null, b: string | null): string | null {
  if (a === null) return b;
  if (b === null) return a;
  return a > b ? a : b;
}

function rollUp(node: FeatureTreeNode): void {
  for (const child of node.children) {
    rollUp(child);
    node.startDate = minDate(node.startDate, child.startDate);
    node.targetDate = maxDate(node.targetDate, child.targetDate);
  }
}

export function buildFeatureTree(items: FeatureTreeItem[]): FeatureTreeNode[] {
  const nodesById = new Map<number, FeatureTreeNode>();
  for (const item of items) {
    nodesById.set(item.id, {
      id: item.id,
      title: item.title ?? `#${item.id}`,
      workItemType: item.work_item_type ?? "Unknown",
      startDate: item.start_date,
      targetDate: item.target_date,
      children: [],
    });
  }

  const roots: FeatureTreeNode[] = [];
  for (const item of items) {
    const node = nodesById.get(item.id)!;
    const parent = item.parent_id !== null ? nodesById.get(item.parent_id) : undefined;
    if (parent) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }

  for (const root of roots) {
    rollUp(root);
  }

  return roots;
}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd apps/web-read && npx vitest run src/utils/buildFeatureTree.test.ts`
Expected: PASS (5 tests)

- [ ] **Step 8: Write the failing test for `ganttMonths`**

Create `apps/web-read/src/utils/ganttMonths.test.ts`:

```ts
import { describe, expect, test } from "vitest";
import { buildGanttMonths, featureCoversMonth } from "./ganttMonths";
import type { FeatureTreeItem } from "../models/feature";

function item(overrides: Partial<FeatureTreeItem>): FeatureTreeItem {
  return {
    id: 1,
    title: "Item",
    work_item_type: "Feature",
    parent_id: null,
    start_date: null,
    target_date: null,
    ...overrides,
  };
}

describe("buildGanttMonths", () => {
  test("spans from the earliest start month to the latest target month", () => {
    const months = buildGanttMonths([
      item({ id: 1, start_date: "2026-01-15T00:00:00", target_date: "2026-02-10T00:00:00" }),
      item({ id: 2, start_date: "2026-03-01T00:00:00", target_date: "2026-04-30T00:00:00" }),
    ]);

    expect(months.map((m) => m.key)).toEqual(["2026-01", "2026-02", "2026-03", "2026-04"]);
  });

  test("ignores features missing either date", () => {
    const months = buildGanttMonths([
      item({ id: 1, start_date: "2026-01-01T00:00:00", target_date: null }),
      item({ id: 2, start_date: null, target_date: "2026-05-01T00:00:00" }),
    ]);

    expect(months).toEqual([]);
  });

  test("returns an empty array for no input", () => {
    expect(buildGanttMonths([])).toEqual([]);
  });

  test("label formats as 'Mon YYYY'", () => {
    const months = buildGanttMonths([
      item({ id: 1, start_date: "2026-01-15T00:00:00", target_date: "2026-01-20T00:00:00" }),
    ]);

    expect(months).toEqual([{ key: "2026-01", label: "Jan 2026" }]);
  });
});

describe("featureCoversMonth", () => {
  test("true when the month falls inside [start, target]", () => {
    const feature = item({ start_date: "2026-01-15T00:00:00", target_date: "2026-03-05T00:00:00" });
    expect(featureCoversMonth(feature, "2026-01")).toBe(true);
    expect(featureCoversMonth(feature, "2026-02")).toBe(true);
    expect(featureCoversMonth(feature, "2026-03")).toBe(true);
  });

  test("false for months outside the range", () => {
    const feature = item({ start_date: "2026-01-15T00:00:00", target_date: "2026-03-05T00:00:00" });
    expect(featureCoversMonth(feature, "2025-12")).toBe(false);
    expect(featureCoversMonth(feature, "2026-04")).toBe(false);
  });

  test("false when either date is missing", () => {
    const feature = item({ start_date: "2026-01-15T00:00:00", target_date: null });
    expect(featureCoversMonth(feature, "2026-01")).toBe(false);
  });
});
```

- [ ] **Step 9: Run test to verify it fails**

Run: `cd apps/web-read && npx vitest run src/utils/ganttMonths.test.ts`
Expected: FAIL — `Cannot find module './ganttMonths'`

- [ ] **Step 10: Implement `ganttMonths`**

Create `apps/web-read/src/utils/ganttMonths.ts`:

```ts
import type { FeatureTreeItem } from "../models/feature";

export interface GanttMonth {
  key: string;
  label: string;
}

const MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function monthKey(isoDate: string): string {
  return isoDate.slice(0, 7);
}

function monthIndex(key: string): number {
  const [year, month] = key.split("-").map(Number);
  return year * 12 + (month - 1);
}

function keyFromIndex(index: number): string {
  const year = Math.floor(index / 12);
  const month = (index % 12) + 1;
  return `${year}-${String(month).padStart(2, "0")}`;
}

function labelFromKey(key: string): string {
  const [year, month] = key.split("-").map(Number);
  return `${MONTH_LABELS[month - 1]} ${year}`;
}

function datedFeatures(items: FeatureTreeItem[]): FeatureTreeItem[] {
  return items.filter(
    (item): item is FeatureTreeItem & { start_date: string; target_date: string } =>
      item.work_item_type === "Feature" && item.start_date !== null && item.target_date !== null
  );
}

export function buildGanttMonths(items: FeatureTreeItem[]): GanttMonth[] {
  const dated = datedFeatures(items);
  if (dated.length === 0) {
    return [];
  }

  let minIndex = Infinity;
  let maxIndex = -Infinity;
  for (const item of dated) {
    minIndex = Math.min(minIndex, monthIndex(monthKey(item.start_date!)));
    maxIndex = Math.max(maxIndex, monthIndex(monthKey(item.target_date!)));
  }

  const months: GanttMonth[] = [];
  for (let i = minIndex; i <= maxIndex; i++) {
    const key = keyFromIndex(i);
    months.push({ key, label: labelFromKey(key) });
  }
  return months;
}

export function featureCoversMonth(item: FeatureTreeItem, monthKeyToCheck: string): boolean {
  if (item.start_date === null || item.target_date === null) {
    return false;
  }
  const target = monthIndex(monthKeyToCheck);
  const start = monthIndex(monthKey(item.start_date));
  const end = monthIndex(monthKey(item.target_date));
  return target >= start && target <= end;
}

export { datedFeatures };
```

- [ ] **Step 11: Run test to verify it passes**

Run: `cd apps/web-read && npx vitest run src/utils/ganttMonths.test.ts`
Expected: PASS (7 tests)

- [ ] **Step 12: Run the full frontend test suite and typecheck**

Run: `cd apps/web-read && npm run test && npx tsc -b --noEmit`
Expected: all vitest tests PASS, `tsc` reports no errors

- [ ] **Step 13: Commit**

```bash
cd apps/web-read
git add package.json package-lock.json src/models/feature.ts src/services/apiReadClient.ts src/utils/buildFeatureTree.ts src/utils/buildFeatureTree.test.ts src/utils/ganttMonths.ts src/utils/ganttMonths.test.ts
git commit -m "feat(web-read): add features-tree data layer with tree and Gantt-month builders"
```

---

### Task 5: `FeaturesRoadmapPage` UI and navigation wiring

**Files:**
- Create: `apps/web-read/src/pages/FeaturesRoadmapPage.tsx`
- Modify: `apps/web-read/src/App.tsx`

**Interfaces:**
- Consumes: `fetchAreaPaths`, `fetchFeaturesTree` (Task 4 + existing `apiReadClient.ts`), `buildFeatureTree`, `FeatureTreeNode` (Task 4), `buildGanttMonths`, `featureCoversMonth`, `GanttMonth`, `datedFeatures` (Task 4), `FeatureTreeItem` (Task 4). Astryx components: `Card`, `HStack`, `Selector`, `Banner`, `EmptyState`, `Spinner`, `Text`, `TreeList`, `Table`, `Badge`, `proportional`, `pixel` (all already used/imported this way in `WorkItemsListPage.tsx`).
- Produces: default-exported `FeaturesRoadmapPage` component, rendered by `App.tsx`. No downstream task consumes anything further from this one — this is the final task.

- [ ] **Step 1: Create the page component**

Create `apps/web-read/src/pages/FeaturesRoadmapPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { Card } from "@astryxdesign/core/Layout";
import { HStack } from "@astryxdesign/core/Layout";
import { Selector } from "@astryxdesign/core/Selector";
import { Table, proportional } from "@astryxdesign/core/Table";
import { Banner } from "@astryxdesign/core/Banner";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Badge } from "@astryxdesign/core/Badge";
import { Text } from "@astryxdesign/core/Text";
import { TreeList, type TreeListItemData } from "@astryxdesign/core/TreeList";
import { fetchAreaPaths, fetchFeaturesTree } from "../services/apiReadClient";
import { buildFeatureTree, type FeatureTreeNode } from "../utils/buildFeatureTree";
import { buildGanttMonths, featureCoversMonth, datedFeatures } from "../utils/ganttMonths";
import type { AreaPath } from "../models/areaPath";
import type { FeatureTreeItem } from "../models/feature";

function formatDate(iso: string | null): string {
  return iso === null ? "—" : iso.slice(0, 10);
}

function toTreeItems(nodes: FeatureTreeNode[]): TreeListItemData[] {
  return nodes.map((node) => ({
    id: String(node.id),
    label: node.title,
    description: `${node.workItemType} · ${formatDate(node.startDate)} → ${formatDate(node.targetDate)}`,
    isExpanded: node.workItemType !== "Feature",
    children: node.children.length > 0 ? toTreeItems(node.children) : undefined,
  }));
}

type GanttRow = { id: number; title: string; coveredMonthKeys: Set<string> } & Record<
  string,
  unknown
>;

export default function FeaturesRoadmapPage() {
  const [areaPaths, setAreaPaths] = useState<AreaPath[]>([]);
  const [areaPathsLoaded, setAreaPathsLoaded] = useState(false);
  const [areaPathId, setAreaPathId] = useState<number | undefined>(undefined);
  const [items, setItems] = useState<FeatureTreeItem[]>([]);
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
    fetchFeaturesTree(areaPathId)
      .then(setItems)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [areaPathId]);

  const tree = buildFeatureTree(items);
  const dated = datedFeatures(items);
  const months = buildGanttMonths(items);
  const excludedCount = items.filter((item) => item.work_item_type === "Feature").length - dated.length;

  const ganttRows: GanttRow[] = dated.map((feature) => ({
    id: feature.id,
    title: feature.title ?? `#${feature.id}`,
    coveredMonthKeys: new Set(months.filter((m) => featureCoversMonth(feature, m.key)).map((m) => m.key)),
  }));

  return (
    <Card>
      <HStack gap={4} align="end" wrap="wrap">
        <Selector
          label="Area path"
          hasSearch
          value={areaPathId !== undefined ? String(areaPathId) : undefined}
          onChange={(value) => setAreaPathId(value ? Number(value) : undefined)}
          options={areaPaths.map((ap) => ({ value: String(ap.id), label: ap.area_path }))}
          width={280}
        />
      </HStack>

      {error && (
        <Banner status="error" title="Error loading features roadmap" description={error} />
      )}

      {areaPathsLoaded && areaPaths.length === 0 && (
        <EmptyState
          title="No area paths configured"
          description="Configure at least one area path in the sync service to see the features roadmap."
        />
      )}

      {!areaPathsLoaded && <Spinner label="Loading area paths" />}

      {areaPathId !== undefined && loading && !error && <Spinner label="Loading features roadmap" />}

      {areaPathId !== undefined && !loading && !error && tree.length === 0 && (
        <EmptyState
          title="No features found"
          description="No Feature, Epic, or Solution work items in this area path."
        />
      )}

      {areaPathId !== undefined && !loading && !error && tree.length > 0 && (
        <>
          <TreeList items={toTreeItems(tree)} density="balanced" />

          {excludedCount > 0 && (
            <Text>
              {excludedCount} feature(s) hidden from the Gantt below for missing start or target date.
            </Text>
          )}

          {ganttRows.length === 0 ? (
            <EmptyState
              title="No features with both start and target dates"
              description="The Gantt chart needs at least one Feature with both dates set."
            />
          ) : (
            <Table
              data={ganttRows}
              idKey="id"
              density="balanced"
              dividers="rows"
              columns={[
                { key: "title", header: "Feature", width: proportional(3) },
                ...months.map((month) => ({
                  key: month.key,
                  header: month.label,
                  width: proportional(1),
                  renderCell: (row: GanttRow) =>
                    row.coveredMonthKeys.has(month.key) ? (
                      <Badge variant="info" label="" />
                    ) : null,
                })),
              ]}
            />
          )}
        </>
      )}
    </Card>
  );
}
```

- [ ] **Step 2: Wire it into navigation**

Modify `apps/web-read/src/App.tsx`. Add `useState` to the React import, import `FeaturesRoadmapPage`, and switch between pages via `SideNavItem.onClick`:

```tsx
import { useState } from "react";
import { Theme } from "@astryxdesign/core/theme";
import { neutralTheme } from "@astryxdesign/theme-neutral";
import { AppShell } from "@astryxdesign/core/AppShell";
import { TopNav } from "@astryxdesign/core/TopNav";
import { TopNavHeading } from "@astryxdesign/core/TopNav";
import { SideNav } from "@astryxdesign/core/SideNav";
import { SideNavItem } from "@astryxdesign/core/SideNav";
import { Banner } from "@astryxdesign/core/Banner";
import WorkItemsListPage from "./pages/WorkItemsListPage";
import FeaturesRoadmapPage from "./pages/FeaturesRoadmapPage";

const INFO_MESSAGE = "";

type Page = "work-items" | "features-roadmap";

export default function App() {
  const [page, setPage] = useState<Page>("work-items");

  return (
    <Theme theme={neutralTheme}>
      <AppShell
        variant="elevated"
        contentPadding={4}
        topNav={
          <TopNav
            label="Main navigation"
            heading={<TopNavHeading heading="Engineering Portfolio" />}
          />
        }
        sideNav={
          <SideNav>
            <SideNavItem
              label="Work Items"
              isSelected={page === "work-items"}
              onClick={() => setPage("work-items")}
            />
            <SideNavItem
              label="Features Roadmap"
              isSelected={page === "features-roadmap"}
              onClick={() => setPage("features-roadmap")}
            />
          </SideNav>
        }
        banner={
          INFO_MESSAGE ? <Banner status="info" title={INFO_MESSAGE} /> : undefined
        }
      >
        {page === "work-items" ? <WorkItemsListPage /> : <FeaturesRoadmapPage />}
      </AppShell>
    </Theme>
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd apps/web-read && npx tsc -b --noEmit`
Expected: no errors. If `Text` or `TreeList` import paths differ from what's used above, fix them to match the actual export path found under `node_modules/@astryxdesign/core/src/Text/index.ts` and `.../TreeList/index.ts` (both already confirmed to export their component and props type from `@astryxdesign/core/TreeList` and `@astryxdesign/core/Text` in this codebase's existing usage conventions — see `WorkItemsListPage.tsx`'s import style for the pattern).

- [ ] **Step 4: Manually verify in the browser**

Run: `cd apps/web-read && npm run dev`, open the printed local URL.
- Click "Features Roadmap" in the side nav — the page renders with the Area Path selector.
- Pick an area path that has Feature/Epic/Solution work items (or Bug/Task-only, to see the `EmptyState`).
- Confirm the tree shows Solution → Epic → Feature nesting (or Solution → Feature directly, if that's how the data is parented) with roll-up dates on parents matching the min/max of their children.
- Confirm the Gantt table below shows one column per month and filled badges only in the months a Feature's `[start_date, target_date]` overlaps.
- Confirm switching back to "Work Items" still works.

Stop the dev server (Ctrl+C) once verified.

- [ ] **Step 5: Commit**

```bash
cd apps/web-read
git add src/pages/FeaturesRoadmapPage.tsx src/App.tsx
git commit -m "feat(web-read): add Features Roadmap page with tree and monthly Gantt"
```

---

## Self-Review Notes

- **Spec coverage:** schema columns + extraction (Task 1) → API flat endpoint (Tasks 2-3) → client tree/Gantt logic (Task 4) → page + nav (Task 5). Roll-up rule, missing-date handling (tree shows `—`, Gantt excludes + count), Area Path scoping, and "Astryx-only" constraint are all implemented and covered by tests or the manual verification step.
- **Placeholder scan:** no TBD/TODO; every step has runnable code or an exact command.
- **Type consistency:** `FeatureTreeItem` (snake_case, matches API JSON) flows unchanged from Task 4's model through `fetchFeaturesTree` into `buildFeatureTree`/`buildGanttMonths`/`FeaturesRoadmapPage`. `FeatureTreeNode` (camelCase, tree-shaped) is only used after `buildFeatureTree` and is consistent between Task 4's implementation/tests and Task 5's `toTreeItems`. `GanttMonth.key` (`"YYYY-MM"`) is produced by `buildGanttMonths` and consumed identically by `featureCoversMonth` and `FeaturesRoadmapPage`.
