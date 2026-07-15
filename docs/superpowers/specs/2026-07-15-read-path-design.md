# Read Path Design: api-read + web-read + Index Review

**Status:** approved
**Date:** 2026-07-15

## Context

`apps/sync-service` is the only writer to Postgres (see `docs/adr/0002-single-writer.md`). The monorepo architecture doc already anticipates two planned apps — `apps/api-read` and `apps/web-read` — plus placeholder shared packages. This spec scaffolds both apps, wires them together, and reviews the current index strategy now that a second (read-heavy) workload exists against the same tables.

## Goals

1. `apps/api-read`: read-only Flask API over the existing Postgres schema.
2. `apps/web-read`: React 19 + TS (Vite) frontend that lists work items via `apps/api-read` only.
3. Objective index review for `work_items` / `work_item_history` under the new read workload, documented with concrete proposals and write-path trade-offs.
4. Documentation: architecture doc, index review doc, two ADRs, two READMEs.

## Non-goals (explicit, to avoid overengineering)

- No authentication/authorization on api-read.
- No separate read-only DB role/credentials yet (documented as a deferred hardening step in the ADR — code-level guardrail only: no write SQL in `apps/api-read`).
- No real CI pipeline — placeholder only.
- No E2E tests, no deploy/infra changes.
- No changes to `apps/sync-service` business logic.

## apps/api-read

**Stack:** Python 3.12+, Flask — matches `apps/sync-service` conventions (factory pattern, raw `psycopg`, no ORM) to minimize atrito.

**Structure** (mirrors sync-service):
```
apps/api-read/
  app/
    __init__.py
    config.py        # env var loading (DATABASE_URL, HOST, PORT)
    db.py            # connection factory only — NO schema/DDL, NO write helpers
    repository.py    # SELECT-only query functions; module docstring states the read-only guardrail
    routes.py         # create_app(conn_factory=...) factory, same DI pattern as sync-service for testability
  requirements.txt
  run.py
  tests/
    test_readonly_guardrail.py   # greps app/ source for INSERT|UPDATE|DELETE|UPSERT, fails if found (excluding this test file itself)
    test_routes.py
  README.md
```

**Endpoints:**
- `GET /health` — liveness check.
- `GET /api/area-paths` — list of area paths (`id`, `organization`, `project`, `area_path`) for populating the frontend filter.
- `GET /api/work-items` — paginated/filtered/sorted listing:
  - Query params: `area_path_id` (optional int), `work_item_type` (optional string), `page` (default 1), `page_size` (default 50, max 200), `order_by` (one of `changed_date`, `id`, `title`; default `changed_date`), `order_dir` (`asc`|`desc`, default `desc`).
  - Response shape (this becomes the shared pagination convention):
    ```json
    {
      "data": [ { "id": 123, "title": "...", "work_item_type": "Bug", "state": "Active", "assigned_to": "...", "changed_date": "...", "area_path_id": 1, "parent_id": null } ],
      "pagination": { "page": 1, "page_size": 50, "total": 812 }
    }
    ```
  - Invalid `order_by` values are rejected with 400 rather than silently falling back, to keep the contract explicit.

**Guardrails:**
- `app/repository.py` module docstring: "This module and this app MUST NOT contain any INSERT/UPDATE/DELETE/UPSERT SQL. apps/sync-service is the only writer."
- `tests/test_readonly_guardrail.py` enforces this mechanically (regex scan of `app/*.py`), so a future PR adding a write statement fails tests, not just review.
- Uses the same `DATABASE_URL` as sync-service for now (no separate role). This is called out as a known gap in the ADR, not silently accepted.

**Config:** `HOST`/`PORT` env vars with sane local defaults (`127.0.0.1:5001`, one port off from sync-service's 5000).

## apps/web-read

**Stack:** Vite + React 19 + TypeScript.

**Structure:**
```
apps/web-read/
  src/
    models/
      workItem.ts        # WorkItem, PaginatedResponse<T> types mirroring api-read's JSON contract
      areaPath.ts
    services/
      apiReadClient.ts   # fetch wrapper, base URL from VITE_API_READ_BASE_URL, no other network calls
    pages/
      WorkItemsListPage.tsx  # table + pagination controls + area-path/type filters + loading/empty/error states
    App.tsx
    main.tsx
  .env.example           # VITE_API_READ_BASE_URL=http://127.0.0.1:5001
  package.json
  README.md
```

- `apiReadClient.ts` is the *only* place that knows the api-read base URL or issues fetches — no component calls `fetch` directly.
- `WorkItemsListPage` handles three explicit UI states: loading (skeleton/spinner), empty (`pagination.total === 0`), error (fetch failure banner with retry).
- No database access of any kind, no other backend calls — enforced by convention/code review since there's only one app to check.

## Shared contracts (packages/shared-contracts)

Populate the previously-placeholder package with a **documentation-level** contract (not a cross-language build artifact, to avoid overengineering a Python/TS packaging bridge):
- `packages/shared-contracts/work-item-listing.md` — the pagination/filter/sort convention (query param names, response envelope shape) that both `apps/api-read` (implements) and `apps/web-read` (consumes) must follow.
- `packages/shared-contracts/schemas/work-item.json` — JSON Schema for the `WorkItem` DTO, used as the source of truth both sides manually mirror (api-read as a `TypedDict`/dataclass shape, web-read as the TS interface).

## Index review (work_items, work_item_history)

**Current state:** no explicit indexes beyond primary keys (`work_items.id`, `work_item_history(work_item_id, rev)`) and the implicit FK on `work_items.area_path_id` (Postgres does **not** auto-index FK columns — this is a real gap, not just theoretical).

**Read-path query patterns introduced by api-read:**
- `WHERE area_path_id = ? [AND work_item_type = ?] ORDER BY changed_date DESC LIMIT/OFFSET` (main listing)
- `SELECT * FROM area_paths` (tiny table, no index needed)
- (future, not built this round) `WHERE work_item_id = ?` on `work_item_history` for a per-item history view — already covered by the composite PK `(work_item_id, rev)` since `work_item_id` is its leading column; **no new index needed there**.

**Proposed indexes:**
1. `CREATE INDEX idx_work_items_area_path_id ON work_items (area_path_id);` — **missing today**, needed for both the read-path filter and existing sync-service reads (`get_work_item_ids`, `delete_work_items` diff logic already filter by this column). Justification: FK columns are not auto-indexed in Postgres; this is the single highest-value index for both read and write paths.
2. `CREATE INDEX idx_work_items_area_path_changed_date ON work_items (area_path_id, changed_date DESC);` — composite, supports the listing's default filter+sort together without a separate sort step. Supersedes the need for a standalone `changed_date` index for the common case.
3. `CREATE INDEX idx_work_items_type ON work_items (work_item_type) WHERE work_item_type IS NOT NULL;` — partial index, only useful when the `work_item_type` filter is used standalone (rare — usually combined with `area_path_id`); kept partial and narrow so it stays cheap to maintain. **Hypothesis, low confidence**: propose but flag as "add only if the filter is used without `area_path_id` in practice" — otherwise index #2 already covers the combined case reasonably via bitmap-and with a type-only scan being marginal. Documented as optional/defer-if-unsure.

**Explicitly NOT proposed (with reasoning):**
- GIN on `raw_json` (JSONB) — no query in api-read or sync-service currently filters on JSONB contents; adding it now is speculative. Flagged as a hypothesis to revisit if a future feature needs it.
- BRIN on `changed_date` or `synced_at` — BRIN pays off on very large, naturally-ordered tables (100k+ rows) with range scans; current table size is unknown/likely small. Documented as a hypothesis to revisit once row counts are known, not applied now.
- Any index on `work_item_history.raw_json` or additional index on `work_item_history` beyond the existing composite PK — no read-path query justifies it yet.

**Write-path impact on sync-service:**
- `upsert_work_items` does one `INSERT ... ON CONFLICT` per item, currently touching the PK btree. Adding indexes #1–#2 adds btree maintenance on every upsert (insert or update path) — for the volumes implied by area-path-scoped syncs (tens–low-thousands of items per run), this is expected to be low-impact relative to the existing per-item round-trip and JSONB write cost. No composite/expression index is proposed on `raw_json`, keeping upsert cost close to today's baseline.
- Recommend applying indexes via a plain `CREATE INDEX IF NOT EXISTS` appended to `SCHEMA_SQL` in `apps/sync-service/app/db.py` (consistent with the existing `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pattern) — sync-service remains the only app that touches DDL, api-read never runs migrations.

**Validation plan:** run `EXPLAIN ANALYZE` on the `/api/work-items` default query before/after index creation against whatever real data exists once api-read is live; if data volume is still small (dev environment), note in the doc that measured benefit may be negligible until production-scale data accumulates — the indexes are still correct to add proactively given they target an unindexed FK.

## Documentation deliverables

1. `docs/architecture/read-path-architecture.md` — flow diagram, app responsibilities, read-only rule, single-writer rule (extends/links `monorepo-architecture.md` rather than duplicating it).
2. `docs/architecture/database-index-review.md` — the index review section above, written out in full with the diagnosis/proposal/validation structure.
3. `docs/adr/0003-read-only-api.md` — decision to build api-read as a code-guardrailed (not DB-role-enforced) read-only service, with the deferred DB-role hardening called out as a known follow-up.
4. `docs/adr/0004-write-path-read-path-separation.md` — decision to keep write path (sync-service) and read path (api-read/web-read) as separate deployable apps rather than adding read endpoints to sync-service.
5. `apps/api-read/README.md` — run instructions, env vars, explicit "this service must never write" statement.
6. `apps/web-read/README.md` — run instructions, structure, integration with api-read.

## Testing & quality baseline

- `apps/api-read`: pytest, same `conn_factory` injection pattern as sync-service's `test_routes.py` for a real Postgres-backed test (reuses `TEST_DATABASE_URL` convention), plus the readonly-guardrail regex test.
- `apps/web-read`: no test framework wired up this round beyond what Vite scaffolds by default (out of scope per non-goals) — noted as a gap in the README, not silently skipped.
- Root-level `package.json`/scripts or per-app scripts (`run-api-read.*`, `run-web-read.*`) to start each app locally — minimal, matching existing `run.py` convention.
- `.env.example` for both new apps.
- CI: placeholder note only (no actual pipeline config), consistent with non-goals.

## Risks / trade-offs

- Using the same `DATABASE_URL` for api-read (no separate role) means the read-only guarantee is enforced by code review + a regex test, not by Postgres permissions. Acceptable for this increment, called out explicitly as technical debt in ADR 0003.
- `packages/shared-contracts` stays documentation-level (Markdown + JSON Schema) rather than a real shared TypeScript/Python package — avoids monorepo tooling complexity (no shared build/publish step) at the cost of manual sync between the two DTO representations. Acceptable given only one DTO shape exists today.
- Index proposal #3 (partial index on `work_item_type`) is flagged low-confidence and may be skipped at implementation time if the plan author judges #1+#2 sufficient.
