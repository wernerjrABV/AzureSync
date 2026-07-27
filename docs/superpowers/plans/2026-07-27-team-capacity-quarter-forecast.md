# Team Capacity Quarter Forecast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Build a read-only Capacity & Flow page that forecasts each Area Path's quarterly delivery range from 12 months of Azure DevOps work-item history.

**Architecture:** sync-service normalizes status intervals from ADO revisions and publishes an atomically replaced JSON snapshot only after a complete history refresh. api-read serves that snapshot through SELECT-only code; web-read renders it through Astryx components. The selected quarter labels the forecast, which always uses the latest complete trailing 12-month snapshot.

**Tech Stack:** Python 3, Flask, PostgreSQL/SQLite fallback, psycopg, React 19, TypeScript, Vite, Vitest, Astryx.

## Global Constraints

- apps/sync-service is the only database writer, and its repository.py is the only write-SQL module.
- apps/api-read must retain SELECT-only SQL and its read-only guardrail.
- Rebuild a snapshot only after zero history-item failures; retain the previous snapshot otherwise.
- Count each eligible item once, at its last Closed, Done, or Resolved transition; exclude Canceled.
- Implement the exact state mapping in docs/superpowers/specs/2026-07-27-team-capacity-quarter-forecast-design.md. Technical Analysis is downstream.
- Forecasts use 12 zero-filled monthly buckets, P25/P50/P75 × 3, and require three delivery months.
- Use Astryx only. Do not add CSS, inline styles, charts, or dependencies.

---

## File structure

- Create apps/sync-service/app/capacity.py — pure revision parsing, state intervals, aggregation, percentiles, and JSON-safe snapshots.
- Create apps/sync-service/tests/test_capacity.py — deterministic flow and forecast tests.
- Modify apps/sync-service/app/db.py, app/repository.py, app/sync_service.py, and tests — persistence and sync publication.
- Modify apps/api-read/app/repository.py, app/routes.py, and tests — SELECT-only snapshot endpoint.
- Create apps/web-read/src/models/capacity.ts and pages/CapacityFlowPage.tsx; modify apiReadClient.ts and App.tsx; add Vitest coverage.

## Task 1: Create the pure flow-analysis module

**Files:**
- Create: apps/sync-service/app/capacity.py
- Create: apps/sync-service/tests/test_capacity.py

**Interfaces:**
- Produces StatusInterval(work_item_id: int, area_path_id: int, revision: int, work_item_type: str, state: str, started_at: datetime, ended_at: datetime).
- Produces build_status_intervals(*, work_item_id: int, area_path_id: int, work_item_type: str, updates: list[dict]) -> list[StatusInterval].

- [ ] **Step 1: Write a failing interval test**

~~~python
def test_build_status_intervals_closes_each_state_at_next_revision():
    intervals = build_status_intervals(
        work_item_id=17, area_path_id=3, work_item_type="User Story",
        updates=[
            update(1, "2026-01-01T09:00:00Z", "New"),
            update(2, "2026-01-02T09:00:00Z", "Development"),
            update(3, "2026-01-04T09:00:00Z", "Waiting Code Review"),
            update(4, "2026-01-05T09:00:00Z", "Development"),
            update(5, "2026-01-06T09:00:00Z", "Closed"),
        ],
    )
    assert [x.state for x in intervals] == [
        "New", "Development", "Waiting Code Review", "Development"
    ]
    assert intervals[1].ended_at == dt("2026-01-04T09:00:00")
~~~

- [ ] **Step 2: Verify it fails**

Run: cd apps/sync-service; pytest tests/test_capacity.py::test_build_status_intervals_closes_each_state_at_next_revision -v

Expected: FAIL because app.capacity does not exist.

- [ ] **Step 3: Implement the minimum pure contract**

~~~python
FINAL_STATES = frozenset({"Closed", "Done", "Resolved"})
CANCELED_STATE = "Canceled"
DEVELOPMENT_TYPES = frozenset({"User Story", "Technical Story", "Bug"})
EXTENDED_TYPES = frozenset({"Feature", "Technical Feature", "Incident", "Problem"})

def state_from_update(update: dict) -> str | None:
    field = update.get("fields", {}).get("System.State")
    return field.get("newValue") if isinstance(field, dict) else None
~~~

Sort revisions by rev, ignore records without a parseable revisedDate or state, and create bounded intervals where a next dated revision exists. Also emit a zero-duration final-state interval at the last valid revision so completion remains observable when no later revision exists. Return no intervals for unsupported types or any item that ever reaches Canceled. Define state_category(type, state) from the approved table; keep Technical Analysis downstream.

- [ ] **Step 4: Add boundary tests and run them**

Add re-opened Closed → Development → Closed, Canceled, missing newValue, invalid revisedDate, and Technical Analysis/downstream assertions.

Run: cd apps/sync-service; pytest tests/test_capacity.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add apps/sync-service/app/capacity.py apps/sync-service/tests/test_capacity.py
git commit -m "feat: derive work item flow intervals"
~~~

## Task 2: Calculate the snapshot and forecast

**Files:**
- Modify: apps/sync-service/app/capacity.py
- Modify: apps/sync-service/tests/test_capacity.py

**Interfaces:**
- Produces build_capacity_snapshot(*, area_path_id: int, intervals: list[StatusInterval], as_of: datetime) -> dict.
- Snapshot fields: generated_at, history_start, monthly_throughput, by_type, forecast, flow_metrics, warnings, is_reliable.

- [ ] **Step 1: Write the failing forecast test**

~~~python
def test_snapshot_uses_last_final_completion_and_quarterly_percentiles():
    snapshot = build_capacity_snapshot(
        area_path_id=3,
        intervals=closed_story_intervals_for_monthly_counts([2, 4, 6]),
        as_of=dt("2026-07-27T00:00:00"),
    )
    story = snapshot["by_type"]["User Story"]
    assert story["forecast"] == {"conservative": 6, "expected": 12, "optimistic": 18}
    assert story["is_reliable"] is True
~~~

- [ ] **Step 2: Verify it fails**

Run: cd apps/sync-service; pytest tests/test_capacity.py::test_snapshot_uses_last_final_completion_and_quarterly_percentiles -v

Expected: FAIL because build_capacity_snapshot does not exist.

- [ ] **Step 3: Implement transparent aggregation**

Build exactly 12 calendar-month buckets ending at as_of. Select the last final-state interval per work item; bucket it by its ended_at month. Compute P25, P50, P75 independently per item type, floor each product after multiplying by 3, and only set is_reliable when three bucket counts are non-zero. Calculate median seconds for every state and aggregate upstream, downstream, and development cycle durations from state_category.

- [ ] **Step 4: Add and run unit coverage**

Test zero-filled months, fewer than three delivery months, type separation, and a reopened item whose last final transition occurs in a later month.

Run: cd apps/sync-service; pytest tests/test_capacity.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add apps/sync-service/app/capacity.py apps/sync-service/tests/test_capacity.py
git commit -m "feat: calculate capacity forecast snapshots"
~~~

## Task 3: Persist intervals and publish snapshots from sync-service

**Files:**
- Modify: apps/sync-service/app/db.py
- Modify: apps/sync-service/app/repository.py
- Modify: apps/sync-service/app/sync_service.py
- Modify: apps/sync-service/tests/conftest.py
- Modify: apps/sync-service/tests/test_db.py
- Modify: apps/sync-service/tests/test_repository.py
- Modify: apps/sync-service/tests/test_sync_service.py

**Interfaces:**
- Produces replace_work_item_status_intervals(conn, *, work_item_id: int, area_path_id: int, intervals: list[StatusInterval]) -> None.
- Produces load_capacity_intervals(conn, *, area_path_id: int) -> list[dict].
- Produces upsert_capacity_snapshot(conn, *, area_path_id: int, payload: dict, generated_at: datetime) -> None.

- [ ] **Step 1: Write failing schema and replacement tests**

~~~python
def test_capacity_snapshot_replaces_previous_complete_version(db_conn):
    repo.upsert_capacity_snapshot(db_conn, area_path_id=1, payload={"version": 1}, generated_at=NOW)
    repo.upsert_capacity_snapshot(db_conn, area_path_id=1, payload={"version": 2}, generated_at=NOW)
    assert repo.get_capacity_snapshot(db_conn, area_path_id=1)["payload"] == {"version": 2}
~~~

Also test that replacing intervals for one item deletes its stale rows, leaving only the supplied revision rows.

- [ ] **Step 2: Verify failure**

Run: cd apps/sync-service; pytest tests/test_db.py tests/test_repository.py -k "capacity or status_interval" -v

Expected: FAIL because tables and repository functions do not exist.

- [ ] **Step 3: Add schema and all write SQL in repository.py**

Add work_item_status_intervals with primary key (work_item_id, revision), area_path/type/state/start/end columns, and index (area_path_id, work_item_type, ended_at). Add capacity_snapshots with one row per Area Path: area_path_id primary key, generated_at, payload JSONB; use TEXT payload in SQLite. Add both tables to PostgreSQL and SQLite schemas and both test-fixture cleanup statements. Keep INSERT, DELETE, and ON CONFLICT SQL only in sync-service repository.py.

- [ ] **Step 4: Wire publishing into _do_sync and prove atomic behavior**

After each successful history upsert, load all stored revisions for that item (not only the current delta), load its current type, rebuild its complete intervals, and replace only that item's stored intervals. After the history loop, build and upsert the snapshot only if any_history_failed is False. On a failed history item, preserve the prior capacity_snapshots payload. Extend test_poison_history_item_does_not_block_other_items_or_checkpoint with that assertion and add a successful follow-up refresh assertion.

Run: cd apps/sync-service; pytest tests/test_db.py tests/test_repository.py tests/test_sync_service.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add apps/sync-service/app/db.py apps/sync-service/app/repository.py apps/sync-service/app/sync_service.py apps/sync-service/tests
git commit -m "feat: persist capacity snapshots after sync"
~~~

## Task 4: Serve snapshots from the read-only API

**Files:**
- Modify: apps/api-read/app/repository.py
- Modify: apps/api-read/app/routes.py
- Modify: apps/api-read/tests/conftest.py
- Modify: apps/api-read/tests/test_repository.py
- Modify: apps/api-read/tests/test_routes.py

**Interfaces:**
- Produces GET /api/capacity?area_path_id=<id>&year=<yyyy>&quarter=<1..4>.
- Success envelope: { data: { ...snapshot, selected_period: { year, quarter } } }; no snapshot: { data: null }.

- [ ] **Step 1: Write failing route coverage**

~~~python
def test_get_capacity_returns_snapshot_and_selected_period(client, db_conn):
    seed_capacity_snapshot(db_conn, area_path_id=7, payload={"forecast": {"expected": 48}})
    response = client.get("/api/capacity?area_path_id=7&year=2026&quarter=3")
    assert response.status_code == 200
    assert response.get_json()["data"]["selected_period"] == {"year": 2026, "quarter": 3}
    assert response.get_json()["data"]["forecast"]["expected"] == 48
~~~

Cover missing Area Path, missing/invalid year, quarter outside 1–4, and an Area Path with no snapshot.

- [ ] **Step 2: Verify failure**

Run: cd apps/api-read; pytest tests/test_routes.py -k capacity -v

Expected: FAIL with 404.

- [ ] **Step 3: Implement SELECT-only retrieval and validation**

~~~python
def get_capacity_snapshot(conn, *, area_path_id: int) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT generated_at, payload FROM capacity_snapshots WHERE area_path_id = %s",
            (area_path_id,),
        )
        return cur.fetchone()
~~~

Require all query parameters in routes.py. Return 400 for invalid input and data:null for a valid request without a snapshot. Merge selected_period into found data only. Do not add write routes or SQL.

- [ ] **Step 4: Run API verification**

Run: cd apps/api-read; pytest tests/test_repository.py tests/test_routes.py tests/test_readonly_guardrail.py -v

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add apps/api-read/app/repository.py apps/api-read/app/routes.py apps/api-read/tests
git commit -m "feat: expose team capacity snapshot"
~~~

## Task 5: Implement the Astryx Capacity & Flow page

**Files:**
- Create: apps/web-read/src/models/capacity.ts
- Modify: apps/web-read/src/services/apiReadClient.ts
- Modify: apps/web-read/src/services/apiReadClient.test.ts
- Create: apps/web-read/src/pages/CapacityFlowPage.tsx
- Create: apps/web-read/src/pages/CapacityFlowPage.test.tsx
- Modify: apps/web-read/src/App.tsx

**Interfaces:**
- Produces fetchCapacity(areaPathId: number, year: number, quarter: number): Promise<CapacitySnapshot | null>.
- Produces CapacityFlowPage using the route response from Task 4.

- [ ] **Step 1: Write failing client and empty-state tests**

~~~tsx
test("shows unavailable forecast for a missing snapshot", async () => {
  vi.mocked(fetchCapacity).mockResolvedValue(null);
  render(<CapacityFlowPage />);
  expect(await screen.findByText("Capacity forecast unavailable")).toBeInTheDocument();
});
~~~

Also assert fetchCapacity(7, 2026, 3) requests /api/capacity?area_path_id=7&year=2026&quarter=3.

- [ ] **Step 2: Verify failure**

Run: cd apps/web-read; npm test -- CapacityFlowPage apiReadClient

Expected: FAIL because the model, client function, and page do not exist.

- [ ] **Step 3: Implement types, retrieval, and page**

Define CapacitySnapshot, ForecastRange, CapacityByType, MonthlyThroughput, FlowMetric, and CapacityWarning in models/capacity.ts. Use URLSearchParams in fetchCapacity and follow existing non-OK error handling.

Use only Card, VStack, HStack, Selector, Banner, EmptyState, Spinner, Table, Badge, and Text. Present month history in an Astryx Table with one column per month; do not add chart CSS. Default the selectors to the current year/quarter, show three forecast cards only when reliable, a type forecast/cycle table, a flow-metric table, and one warning Banner per API warning. Add the Capacity & Flow SideNavItem and capacity-flow page discriminator in App.tsx.

- [ ] **Step 4: Run UI and build verification**

Add tests for loading, API error, no Area Paths, no snapshot, warnings, and reliable data.

Run: cd apps/web-read; npm test -- CapacityFlowPage apiReadClient; npm run build

Expected: PASS.

- [ ] **Step 5: Commit**

~~~bash
git add apps/web-read/src/models/capacity.ts apps/web-read/src/services/apiReadClient.ts apps/web-read/src/services/apiReadClient.test.ts apps/web-read/src/pages/CapacityFlowPage.tsx apps/web-read/src/pages/CapacityFlowPage.test.tsx apps/web-read/src/App.tsx
git commit -m "feat: add capacity and flow dashboard"
~~~

## Task 6: Verify the vertical slice and document operation

**Files:**
- Modify: apps/sync-service/README.md
- Modify: apps/api-read/README.md
- Modify: apps/web-read/README.md

- [ ] **Step 1: Add operator documentation**

State in the three READMEs that the first complete history backfill is required, forecasts require three months containing completed eligible work, Canceled items are excluded, and reopens count at the last final transition. Add the capacity endpoint and page to the corresponding app docs.

- [ ] **Step 2: Run sync-service tests**

Run: cd apps/sync-service; pytest tests/test_capacity.py tests/test_db.py tests/test_repository.py tests/test_sync_service.py -v

Expected: PASS when TEST_DATABASE_URL is set; otherwise the existing documented skip.

- [ ] **Step 3: Run api-read tests**

Run: cd apps/api-read; pytest tests/test_repository.py tests/test_routes.py tests/test_readonly_guardrail.py -v

Expected: PASS when TEST_DATABASE_URL is set; otherwise the existing documented skip.

- [ ] **Step 4: Run frontend tests and build**

Run: cd apps/web-read; npm test; npm run build

Expected: PASS and build exits 0.

- [ ] **Step 5: Commit**

~~~bash
git add apps/sync-service/README.md apps/api-read/README.md apps/web-read/README.md
git commit -m "docs: explain capacity forecast workflow"
~~~

## Plan self-review

- Spec coverage: Tasks 1–2 cover mapping, reopens, cancelation, 12-month throughput, percentiles, reliability, and flow diagnostics. Task 3 upholds single-writer and complete-snapshot rules. Task 4 preserves the read path. Task 5 implements the approved Astryx-only page. Task 6 verifies and documents operation.
- Placeholder scan: every step has an explicit command, assertion, or implementation detail; no deferred work remains.
- Type consistency: Task 1 outputs StatusInterval; Task 2 outputs a snapshot; Task 3 persists it; Task 4 returns it; Task 5 consumes it.
