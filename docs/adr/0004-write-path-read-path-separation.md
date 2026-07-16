# ADR 0004: Write path and read path are separate apps

**Status:** Accepted
**Date:** 2026-07-15

## Context

Once read-only listing is needed, the read logic could live inside
`apps/sync-service` (adding GET routes there) or in a new, separate app.

## Decision

Read endpoints live in a new app, `apps/api-read`, not inside
`apps/sync-service`. `apps/sync-service` gains no new routes as part of
this work.

## Rationale

- Keeps the single-writer guarantee (ADR 0002) structurally obvious: the
  writer process and the reader process are different deployables, not
  different code paths inside one process.
- Lets each app scale/deploy independently — sync-service runs a
  background scheduler and does periodic bursty writes; api-read serves
  ad-hoc read traffic. Coupling them would force one deployment cadence
  for both.
- Matches the plan already laid out in
  `docs/architecture/monorepo-architecture.md`, which reserved
  `apps/api-read` and `apps/web-read` as planned apps from the start.

## Consequences

- Positive: no risk of a read endpoint accidentally sharing a code path
  with a write helper in `apps/sync-service/app/repository.py`.
- Negative: some duplication of low-level patterns (connection handling,
  Flask factory shape) between the two apps — accepted since each app's
  `repository.py` is intentionally small and the duplication is boilerplate,
  not business logic.
