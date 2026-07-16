# Database Index Review — Read Path

**Date:** 2026-07-15
**Context:** `apps/api-read` introduces a new read-heavy query pattern
against the same tables `apps/sync-service` writes to. This document
reviews the current index state and proposes changes.

## Central tables

- `work_items` — one row per Azure DevOps work item, scoped by
  `area_path_id`. Central table for the read path.
- `work_item_history` — one row per `(work_item_id, rev)`, not FK'd to
  `work_items` (history survives item deletion from scope).
- `area_paths` — small config table, no indexing concerns.

## Read-path query patterns (from `apps/api-read/app/repository.py`)

- `WHERE area_path_id = ? [AND work_item_type = ?] ORDER BY changed_date DESC LIMIT ? OFFSET ?`
  — the default `/api/work-items` listing query.
- `SELECT * FROM area_paths ORDER BY id` — tiny table, no index needed.

## Diagnosis (before this change)

| Index | Status |
|---|---|
| `work_items` PK on `id` | existing |
| `work_item_history` PK on `(work_item_id, rev)` | existing — covers `WHERE work_item_id = ?` lookups since `work_item_id` is the leading PK column |
| `work_items.area_path_id` (FK to `area_paths`) | **missing** — Postgres does not auto-index FK columns |
| `work_items.changed_date` | missing |
| `work_items.work_item_type` | missing |

The missing `area_path_id` index affects both the new read path and
existing sync-service reads (`get_work_item_ids`, and the ID-diff logic in
`sync_service.run_sync` that filters by `area_path_id`).

## Proposed indexes (implemented in `apps/sync-service/app/db.py`)

1. `idx_work_items_area_path_id ON work_items (area_path_id)` — highest
   value: fixes the missing FK index, benefits both read and write paths.
2. `idx_work_items_area_path_changed_date ON work_items (area_path_id, changed_date DESC)`
   — composite index supporting the listing's default filter+sort together
   in one index scan.
3. `idx_work_items_type ON work_items (work_item_type) WHERE work_item_type IS NOT NULL`
   — partial index for the case where `work_item_type` is filtered without
   `area_path_id`. **Low-confidence / optional**: usage of this filter
   combination in practice is a hypothesis, not observed data. Revisit
   after api-read has real traffic; drop if unused.

## Explicitly not proposed (hypotheses, revisit later)

- **GIN on `work_items.raw_json`** — no current query (read or write path)
  filters on JSONB contents. Speculative; add only when a concrete feature
  needs it.
- **BRIN on `changed_date` / `synced_at`** — pays off on large
  (100k+ row), naturally time-ordered tables with range scans. Current row
  counts are unknown/likely small in this deployment; revisit once volume
  is known.
- **Additional index on `work_item_history`** — no read-path query
  introduced by api-read this round needs anything beyond the existing
  composite PK.

## Write-path impact on sync-service

`repository.upsert_work_items` performs one `INSERT ... ON CONFLICT` per
item. Adding indexes 1–2 adds btree maintenance to every upsert. For the
per-area-path sync volumes this system targets (tens to low thousands of
items per run), this is expected to be low relative to the existing
per-item round-trip and JSONB write cost. No index touches `raw_json`, so
the most expensive column to write is unaffected.

## Validation plan

Run `EXPLAIN ANALYZE` on the default `/api/work-items` query
(`SELECT ... FROM work_items WHERE area_path_id = ? ORDER BY changed_date DESC LIMIT 50 OFFSET 0`)
before and after deploying these indexes against real data once
`apps/api-read` is live. In a low-row-count dev environment the measured
benefit may be negligible — the indexes are still correct to add
proactively given index 1 fixes a genuinely unindexed FK column.
