# Monorepo Architecture

## Overview

This repository is structured as an enterprise monorepo under `apps/` and
`packages/`. Today it contains one app, `apps/sync-service`, which is both
the data ingestion pipeline and the only database writer.

## App responsibilities

| App | Responsibility | DB access |
|---|---|---|
| `apps/sync-service` | Poll Azure DevOps, normalize, persist work items/history/checkpoints | **read + write** (only writer) |
| `apps/api-read` | Serve read-only queries over the same database | read-only |
| `apps/web-read` (planned) | List data to end users via `apps/api-read` | none (HTTP client of api-read only) |

## The single-writer rule

`apps/sync-service` is the only app permitted to execute
INSERT/UPDATE/DELETE/UPSERT/operational-migration SQL. This is enforced
today by convention and documentation (see `docs/adr/0002-single-writer.md`)
since no other app exists yet to violate it. When `apps/api-read` is
scaffolded, it must:

- open its own read-only connection role/credentials where the database
  supports it (e.g. Postgres `REVOKE INSERT, UPDATE, DELETE ON ALL TABLES`
  for that role), and
- contain no SQL statement of type INSERT/UPDATE/DELETE anywhere in its
  codebase (enforceable later via a CI grep/lint step once that app exists).

## Data flow

```
Azure DevOps REST API
        │
        ▼
apps/sync-service  (WIQL + batch fetch → normalize → upsert)
        │  writes
        ▼
   PostgreSQL
        │  reads
        ▼
apps/api-read       (read-only query layer)
        │  HTTP
        ▼
apps/web-read       (listing UI, planned)
```

## Shared packages

`packages/*` are placeholders today (see each package's README). They exist
so that when `apps/api-read` is built, contracts/config/observability
conventions have an obvious home instead of being duplicated per-app or
bolted onto `apps/sync-service`.

## Evolution principle

Each new app or package lands via its own design spec
(`docs/superpowers/specs/`) and implementation plan
(`docs/superpowers/plans/`) — incremental delivery, no big-bang rewrite of
the existing sync-service.
