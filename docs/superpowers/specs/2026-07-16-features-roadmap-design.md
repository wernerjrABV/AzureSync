# Features Roadmap (tree + Gantt) — Design

## Goal

A new page listing Features in a tree under their parent (Epic or Solution), each
showing `start_date`/`target_date`. Parent nodes (Epic, Solution) roll up dates
from their children: `start_date = min(children.start_date)`,
`target_date = max(children.target_date)`. Below the tree, a Gantt visualization
of the same data, scoped to the selected Area Path, built entirely from Astryx
design system components (no custom CSS, per project rule).

## Data model (apps/sync-service)

`work_items` gains two columns, added the same way `parent_id` was added
(`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `db.py`'s `SCHEMA_SQL`):

```sql
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS start_date TIMESTAMP;
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS target_date TIMESTAMP;
```

`ado_client._map_work_item` extracts `Microsoft.VSTS.Scheduling.StartDate` and
`Microsoft.VSTS.Scheduling.TargetDate` from `fields`, reusing the same
date-parsing logic already applied to `System.ChangedDate` (strip fractional
seconds / trailing `Z`, parse as naive `datetime`). Both fields are optional —
`None` when ADO has no value.

`repository.py`'s upsert (`upsert_work_item` or equivalent) is extended to
write `start_date` and `target_date`. No backfill script is needed: syncs are
idempotent and the next scheduled sync per area path re-upserts every item,
populating the new columns for existing rows.

## API (apps/api-read)

New endpoint: `GET /api/features-tree?area_path_id=<id>`

- Requires `area_path_id` (400 if missing, same pattern as `/api/work-items`).
- Returns a **flat list** (tree assembly happens client-side) of every work
  item in that area path whose `work_item_type` is `Feature`, `Epic`, or
  `Solution`:
  ```json
  {
    "data": [
      {
        "id": 123,
        "title": "...",
        "work_item_type": "Feature",
        "parent_id": 45,
        "start_date": "2026-01-10T00:00:00",
        "target_date": "2026-02-28T00:00:00"
      }
    ]
  }
  ```
- `repository.py` adds `list_features_tree(conn, *, area_path_id)`: a single
  `SELECT id, title, work_item_type, parent_id, start_date, target_date FROM
  work_items WHERE area_path_id = %s AND work_item_type IN ('Feature',
  'Epic', 'Solution') ORDER BY id`. Read-only, consistent with
  `docs/adr/0003-read-only-api.md`.
- No pagination — Feature/Epic/Solution volume per area path is expected to
  be small relative to all work items (unlike the work-items list).

## Frontend (apps/web-read)

### Tree assembly (client-side, new `services/`/`models/` helper)

Given the flat list:
1. Build parent→children map from `parent_id`. A `Feature`'s parent may be
   either an `Epic` or a `Solution` directly — the tree-building code does
   not assume a fixed depth.
2. Roots are nodes whose `parent_id` is `null`/not present in the fetched
   set (i.e., `Solution`s, or an `Epic`/`Feature` whose parent wasn't
   returned — e.g. out of scope type).
3. Compute rolled-up dates bottom-up: a parent's `start_date` is the min of
   its own value (if any) and all descendants' `start_date`; `target_date`
   is the max, symmetrically. A parent with no dated descendants and no own
   dates shows `—`.
4. Leaves (`Feature`s) show their own `start_date`/`target_date` — no
   roll-up needed since they have no children by definition.

### Page: `FeaturesRoadmapPage.tsx`

New `SideNavItem` ("Features Roadmap") alongside "Work Items" in `App.tsx`.

- Same `Selector` for Area Path as `WorkItemsListPage`, reused/extracted if
  convenient.
- `TreeList` rendering the assembled tree: `label` = title, `description` =
  `${work_item_type} · ${startDate ?? "—"} → ${targetDate ?? "—"}`.
  Epics/Solutions expanded by default (`isExpanded: true`).
- Below the tree, in the same `Card`: a Gantt built as an Astryx `Table`:
  - Column 1: "Feature" (`proportional(3)`), listing every `Feature` that has
    **both** `start_date` and `target_date` (flat list, not the tree —
    Epics/Solutions aren't rendered as Gantt rows).
  - One additional column per calendar month spanning from the earliest
    `start_date` to the latest `target_date` across all qualifying features
    in the area path, each `proportional(1)`, header = `"MMM yyyy"`.
  - Cell content: a filled `Badge` (or `ProgressBar` at `value=100`) when the
    feature's `[start_date, target_date]` range overlaps that calendar
    month, otherwise empty. No partial-month sub-division — monthly
    resolution only, entirely via Astryx `Table`/`Badge` props (no pixel
    math, no inline styles).
  - If zero features have both dates, the Gantt section is replaced by an
    `EmptyState` ("No features with both start and target dates").
- Features missing either date are excluded from the Gantt only; the tree
  above still shows them (with `—` for the missing date). A short `Text`
  note under the tree states how many features were excluded from the
  Gantt for missing dates (0 → note omitted).

### Loading/error states

Mirror `WorkItemsListPage`: `Spinner` while loading, `Banner status="error"`
on fetch failure, `EmptyState` when the area path has no Feature/Epic/
Solution items.

## Out of scope

- No editing of dates — read-only page, consistent with the rest of the app.
- No cross-area-path view — Gantt/tree is always scoped to one selected
  Area Path.
- No sub-month (weekly/daily) Gantt resolution.
- No new dependency (no charting library) — Astryx components only.
