# ADR 0001: Adopt a monorepo layout

## Status

Accepted — 2026-07-15

## Context

The codebase was a single Flask app at the repository root. The roadmap
requires adding a read-only backend and a frontend that consume the same
data, plus shared packages (contracts, config, observability, DB
guidelines) as the system grows. Keeping everything in one flat Python
package would blur ownership boundaries between the app that writes to the
database and the apps that will only read from it.

## Decision

Restructure the repository into a monorepo with `apps/*` for deployable
services and `packages/*` for shared, non-deployable code. The existing
Flask app moves to `apps/sync-service` with no behavior change — a pure
`git mv`, no logic rewrite.

## Consequences

- Positive: clear place for `apps/api-read` and `apps/web-read` to land
  later without restructuring again.
- Positive: `packages/*` gives shared contracts/config a home instead of
  being duplicated once a second app exists.
- Negative: one-time path churn (CI configs, local run instructions,
  IDE working directories) for the existing app — mitigated by updating
  `CLAUDE.md`/`README.md` in the same change.
- Neutral: no runtime behavior changes; this ADR only affects repository
  layout.
