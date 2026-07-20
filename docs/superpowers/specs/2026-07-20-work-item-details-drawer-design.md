# Work Item Details Drawer

## Goal

When a user clicks a row in the Work Items screen, open an Astryx right-side drawer containing the complete work item detail, including the current stored fields, the original Azure DevOps payload, and all stored history revisions.

## Design

The read API will expose `GET /api/work-items/<id>`. The repository will retrieve one current row from `work_items` and its revisions from `work_item_history`, ordered by revision ascending. The response will be an object with `data` containing the current item and `history` containing revision records. A missing item returns a 404 JSON error. This remains read-only and does not alter the single-writer boundaries.

The current item response will include all columns relevant to the work item (`id`, `area_path_id`, title, type, state, assignee, changed/created/activated/closed/start/target dates, parent ID, `raw_json`, and `synced_at`). Each history record will include `work_item_id`, `area_path_id`, `rev`, `revised_by`, `revised_date`, `raw_json`, and `synced_at`.

The web client will add a typed `fetchWorkItemDetails(id)` function and models for the detail response. `WorkItemsListPage` will track the selected row, detail loading state, and detail error. Clicking any table row requests the detail and opens the drawer; changing or closing the drawer clears the selection. The list query and pagination behavior remain unchanged.

The drawer will use the same Astryx `Dialog` positioning and `DialogHeader` pattern as the Feature Roadmap. It will show a concise current-field section, a formatted JSON payload section, and a revision section where each revision exposes its metadata and formatted JSON payload. Null values use the existing em-dash convention. Long JSON and revision content must remain readable within the drawer using existing Astryx layout/text components and available application primitives; no new bespoke visual system is introduced.

## States and failure handling

- Before a detail response arrives, the drawer remains open and shows an Astryx spinner.
- If the detail request fails, the drawer remains open and shows an Astryx error banner with a close action.
- Selecting another row replaces the selected item and ignores stale responses from an older selection.
- Closing the drawer cancels the visible selection and does not affect the list query.

## Testing

API repository tests will cover current-item and ordered-history retrieval and the missing-item case. Route tests will cover the 200 response envelope and 404 response. Frontend tests will cover the client request shape and the row-click/detail state behavior using the existing project test conventions. The web application build and relevant test suites must pass.

## Scope

This change does not modify sync behavior, schema, list pagination, search, ordering, or the existing Feature Roadmap drawer. It adds only read-path detail retrieval and its Work Items UI presentation.
