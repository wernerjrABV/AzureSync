# shared-contracts

**Status:** placeholder — not yet in use.

Will hold DTOs, schemas, and event/type contracts shared between
`apps/sync-service` (writer) and future read-side apps (`apps/api-read`,
`apps/web-read`), so the read side never has to reverse-engineer the
database schema directly.

Populated when `apps/api-read` is scaffolded (see
`docs/architecture/monorepo-architecture.md`).
