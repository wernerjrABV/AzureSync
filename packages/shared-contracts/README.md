# shared-contracts

Documentation-level contracts shared between `apps/api-read` (writer of
the HTTP contract) and `apps/web-read` (consumer). Not a built/published
package — each side manually mirrors these shapes in its own language
(Python dict shapes in api-read, TypeScript interfaces in web-read).

- `work-item-listing.md` — pagination/filter/sort query contract and
  response envelope for `GET /api/work-items`.
- `schemas/work-item.json` — JSON Schema for the `WorkItem` DTO.
