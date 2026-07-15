# Read Path Architecture

## Flow

```
Azure DevOps REST API
        │
        ▼
apps/sync-service   (WIQL + batch fetch → normalize → upsert; ONLY writer)
        │  writes
        ▼
   PostgreSQL
        │  reads
        ▼
apps/api-read        (Flask; SELECT-only; DATABASE_URL, no separate role yet)
        │  HTTP JSON (GET /api/work-items, GET /api/area-paths)
        ▼
apps/web-read        (Vite + React 19 + TS; only network dependency is api-read)
```

## Responsibilities

| App | Reads DB? | Writes DB? | Talks to |
|---|---|---|---|
| `apps/sync-service` | yes | yes (only writer) | Azure DevOps REST, Postgres |
| `apps/api-read` | yes (SELECT only) | no | Postgres |
| `apps/web-read` | no | no | `apps/api-read` (HTTP only) |

## Rules

1. **Single-writer rule** (`docs/adr/0002-single-writer.md`): only
   `apps/sync-service` executes INSERT/UPDATE/DELETE/UPSERT/DDL SQL.
2. **Read-only API rule** (`docs/adr/0003-read-only-api.md`):
   `apps/api-read` contains zero write SQL, mechanically enforced by
   `apps/api-read/tests/test_readonly_guardrail.py`.
3. **Frontend isolation rule**: `apps/web-read` never talks to Postgres
   directly and never calls any backend other than `apps/api-read`.

## Shared contract

`apps/api-read` and `apps/web-read` share the listing contract documented
in `packages/shared-contracts/work-item-listing.md` and the DTO shape in
`packages/shared-contracts/schemas/work-item.json`.
