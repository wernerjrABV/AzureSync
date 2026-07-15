# ADR 0002: sync-service is the only database writer

## Status

Accepted — 2026-07-15

## Context

The roadmap adds a read-only backend (`apps/api-read`) and a frontend
(`apps/web-read`) that will query the same PostgreSQL database that
`apps/sync-service` populates. Without an explicit rule, it would be easy
for a future read-side feature to "just add an UPDATE" directly against the
database, creating two independent writers with no shared transaction
boundary, checkpoint logic, or idempotency guarantees.

## Decision

`apps/sync-service` is the only app in this monorepo permitted to execute
write SQL (INSERT/UPDATE/DELETE/UPSERT) or run data migrations against the
operational database. `apps/api-read` and `apps/web-read` (and any future
read-side app) may only read.

This is documented today (this ADR, `apps/sync-service/README.md`,
`docs/architecture/monorepo-architecture.md`) since `apps/api-read` does not
exist yet to enforce it against. When `apps/api-read` is scaffolded, its own
implementation plan must include:

- a read-only database role/credential for that app, and
- a CI check (e.g. grep for `INSERT INTO`/`UPDATE `/`DELETE FROM` outside
  `apps/sync-service`) to catch violations before merge.

## Consequences

- Positive: one place owns transaction boundaries, locking
  (`try_acquire_lock`), and checkpoint semantics — no cross-app write
  races.
- Positive: read-side apps can be scaled, redeployed, or rewritten
  independently without any risk of corrupting sync state.
- Negative: any feature that needs to write derived/aggregated data (e.g. a
  future reporting rollup) must be built as a feature of `sync-service` (or
  a new writer app, which would need its own ADR), not bolted onto the read
  side.
