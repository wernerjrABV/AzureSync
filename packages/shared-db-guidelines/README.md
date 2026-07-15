# shared-db-guidelines

**Status:** placeholder — not yet in use.

Will hold documentation and (if needed) utilities describing how the
read-only side (`apps/api-read`) is allowed to query the database that
`apps/sync-service` owns and writes — index usage guidance, allowed query
patterns, and the boundary that no read-side code issues write SQL.

Populated alongside `docs/architecture/database-index-review.md` when the
index review spec lands.
