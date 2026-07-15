# Work Item Listing Contract

Implemented by `apps/api-read` (`GET /api/work-items`), consumed by
`apps/web-read`. Any change to this contract must update both sides.

## Request (query params)

| Param | Type | Default | Notes |
|---|---|---|---|
| `area_path_id` | int | none (no filter) | optional |
| `work_item_type` | string | none (no filter) | optional |
| `page` | int | `1` | 1-indexed |
| `page_size` | int | `50` | max `200` |
| `order_by` | `changed_date`\|`id`\|`title` | `changed_date` | invalid value → 400 |
| `order_dir` | `asc`\|`desc` | `desc` | invalid value → 400 |

## Response

```json
{
  "data": [ /* array of WorkItem, see schemas/work-item.json */ ],
  "pagination": { "page": 1, "page_size": 50, "total": 812 }
}
```

## WorkItem shape

See `schemas/work-item.json` for the authoritative field list and types.
`apps/api-read`'s `repository.list_work_items` and `apps/web-read`'s
`src/models/workItem.ts` must both mirror this shape manually — there is
no shared build artifact between the two languages in this increment.

## Area paths

`GET /api/area-paths` returns `[{ "id": int, "organization": str, "project": str, "area_path": str }]`, no pagination envelope (small, unbounded list).
