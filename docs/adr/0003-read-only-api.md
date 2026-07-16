# ADR 0003: Read-only API enforced by code guardrail, not DB role

**Status:** Accepted
**Date:** 2026-07-15

## Context

`apps/api-read` needs a hard guarantee that it never writes to the
database, so the single-writer rule (ADR 0002) holds even as a second app
gains DB access.

## Decision

For this increment, `apps/api-read` enforces read-only behavior at the
code level:
- No INSERT/UPDATE/DELETE/UPSERT SQL anywhere in `apps/api-read/app/`,
  mechanically checked by `tests/test_readonly_guardrail.py` (regex scan,
  fails the test suite if violated).
- `apps/api-read` uses the same `DATABASE_URL` as `apps/sync-service` —
  there is **no separate Postgres role** with `REVOKE INSERT, UPDATE,
  DELETE` applied yet.

## Consequences

- Positive: ships quickly, no infra/credential provisioning blocking the
  read path.
- Negative: the read-only guarantee is enforced by test + code review, not
  by the database itself. A bug that somehow introduces write SQL would be
  caught by CI (once real CI exists), not prevented by Postgres.

## Follow-up (deferred, not scheduled)

Introduce a dedicated Postgres role for `apps/api-read` with
`GRANT SELECT` only (`REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES
FROM api_read_role`), and point `apps/api-read` at a separate
`DATABASE_URL` using that role. Tracked as technical debt; not required for
this increment per the read-path design spec's explicit non-goals.
