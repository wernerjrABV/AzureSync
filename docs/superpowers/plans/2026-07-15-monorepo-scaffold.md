# Monorepo Scaffold + sync-service Reposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the existing Flask app into `apps/sync-service/`, scaffold empty `packages/*` placeholders, and add the architecture/ADR docs that make the monorepo layout and single-writer rule explicit — without changing any application behavior.

**Architecture:** Pure `git mv` of the existing `app/`, `run.py`, `requirements.txt`, `tests/` into `apps/sync-service/`. No import changes needed (all internal imports are already `app.X`-absolute and move together). New docs and placeholder package READMEs are additive only.

**Tech Stack:** Python 3.12+, Flask, psycopg, pytest (unchanged).

## Global Constraints

- Do not modify any Python source logic — this is a structural move only, per the approved spec's "no rewrite" constraint.
- Preserve uncommitted changes in `app/ado_client.py`, `app/db.py`, `app/repository.py` — they must move with `git mv`, not be discarded.
- `apps/api-read/` and `apps/web-read/` are NOT created in this plan (out of scope per spec).
- All doc content must be written in full now — no "TBD" sections.

---

### Task 1: Move sync-service files with git mv

**Files:**
- Move: `run.py` → `apps/sync-service/run.py`
- Move: `requirements.txt` → `apps/sync-service/requirements.txt`
- Move: `app/` → `apps/sync-service/app/`
- Move: `tests/` → `apps/sync-service/tests/`
- Create: `apps/sync-service/README.md`

**Interfaces:**
- Produces: working directory `apps/sync-service/` from which `python run.py` and `pytest` run exactly as they did from repo root before the move.

- [ ] **Step 1: Check git status before moving anything**

Run: `git status`
Expected: shows the pre-existing modifications to `app/ado_client.py`, `app/db.py`, `app/repository.py` as tracked modifications (not untracked) — confirms `git mv` will carry them along correctly.

- [ ] **Step 2: Create the target directory and move files with git mv**

```bash
mkdir -p apps/sync-service
git mv app apps/sync-service/app
git mv run.py apps/sync-service/run.py
git mv requirements.txt apps/sync-service/requirements.txt
git mv tests apps/sync-service/tests
```

- [ ] **Step 3: Verify the app still runs from its new location**

```bash
cd apps/sync-service
python run.py &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5000
kill %1
cd ../..
```
Expected: prints `200`.

- [ ] **Step 4: Verify tests still pass from the new location**

Run (requires `TEST_DATABASE_URL` set, same as before the move):
```bash
cd apps/sync-service
pytest
cd ../..
```
Expected: same pass/skip result as running `pytest` from repo root did before the move (tests skip cleanly if `TEST_DATABASE_URL` is unset — no new failures introduced by the move).

- [ ] **Step 5: Write apps/sync-service/README.md**

```markdown
# sync-service

Syncs Azure DevOps work items into PostgreSQL, scoped per area path.

## Ownership

**This is the only service in the monorepo authorized to write to the
database** (INSERT / UPDATE / DELETE / UPSERT / operational data
migrations). See `docs/adr/0002-single-writer.md`.

Responsibilities:
- Poll Azure DevOps (WIQL + work item batch REST calls) per area path.
- Normalize and upsert work items, work item history, and checkpoints.
- Own the Postgres schema (`app/db.py`).

Consumers that need to read this data (future `api-read`, dashboards,
reports) must go through a read-only service — never connect directly to
this database from another app.

## Setup

1. Set Windows environment variables:
   - `DATABASE_URL` — e.g. `postgresql://user:pass@localhost:5432/azure_sync`
   - `AZURE_DEVOPS_API_KEY` — your Azure DevOps Personal Access Token
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run:
   ```
   python run.py
   ```
4. Open http://127.0.0.1:5000

## Running tests

Requires a local Postgres test database:
```
createdb azure_sync_test
set TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/azure_sync_test
pytest
```

## Usage

- Add an area path via the form on the home page (organization, project, area path, include sub-paths, active, interval in minutes).
- First sync for a new area path is a full load; subsequent syncs are incremental and remove items no longer in scope.
- Click "Sincronizar agora" to trigger a sync manually — disabled while a sync is already running for that area path.
- A red banner appears at the top if any area path's last sync failed due to an invalid/expired token — check `AZURE_DEVOPS_API_KEY`.
```

- [ ] **Step 6: Commit**

```bash
git add apps/sync-service
git commit -m "refactor: move sync app into apps/sync-service (monorepo scaffold)"
```

---

### Task 2: Update root CLAUDE.md and README.md for the new layout

**Files:**
- Modify: `CLAUDE.md` (repo root)
- Modify: `README.md` (repo root)

**Interfaces:**
- Consumes: nothing from Task 1 code-wise; depends on Task 1 having completed the move so paths in the docs are accurate.

- [ ] **Step 1: Rewrite root CLAUDE.md**

Replace the full contents of `CLAUDE.md` with:

```markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Monorepo layout

This is an enterprise monorepo. See `docs/architecture/monorepo-architecture.md`
for the full picture. Today it contains one app:

- `apps/sync-service/` — the only service authorized to write to the
  database. See `apps/sync-service/README.md` and its own `CLAUDE.md`-style
  guidance below.

Planned next (not yet scaffolded — see `docs/architecture/monorepo-architecture.md`):
- `apps/api-read/` — read-only backend
- `apps/web-read/` — frontend that lists data via `apps/api-read`

## Commands (apps/sync-service)

```bash
cd apps/sync-service

# Install dependencies
pip install -r requirements.txt

# Run the app (http://127.0.0.1:5000)
python run.py

# Run tests (requires a local Postgres test DB)
createdb azure_sync_test
set TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/azure_sync_test
pytest

# Run a single test file / test
pytest tests/test_sync_service.py
pytest tests/test_sync_service.py::test_name -v
```

Required environment variables (Windows env vars, not a `.env` file):
- `DATABASE_URL` — Postgres connection string for the app's own DB.
- `TEST_DATABASE_URL` — separate Postgres DB used only by `tests/conftest.py`; tests are skipped if unset.
- `AZURE_DEVOPS_API_KEY` — Azure DevOps PAT used by `AdoClient`.

## Architecture (apps/sync-service)

Flask app that polls Azure DevOps (via WIQL + work item batch REST calls) and syncs work items into Postgres, scoped per **area path**. Each area path is a row with its own schedule, lock, and checkpoint — the whole system is designed to run many of these concurrently and independently.

Module responsibilities (`apps/sync-service/app/`):
- `ado_client.py` — thin Azure DevOps REST wrapper. Handles auth (Basic w/ PAT), retries on 429/5xx with `Retry-After` support, and raises `AdoAuthError` (401) / `AdoRetryExhaustedError` (retries exhausted) so callers can distinguish failure modes. `get_changed_ids` uses **date precision, not datetime** in the WIQL `ChangedDate` filter (ADO rejects a time component) — re-fetching a whole day is intentional and safe because upserts are idempotent.
- `repository.py` — all SQL, using raw `psycopg` (no ORM). Every function takes a `conn` and does not commit; callers control transaction boundaries. This is the only file in the monorepo that issues write SQL (INSERT/UPDATE/DELETE/UPSERT) — see `docs/adr/0002-single-writer.md`.
- `sync_service.run_sync` — orchestrates one sync for one area path:
  1. `try_acquire_lock` (DB-row-based lock via `is_running` flag) — returns `skipped_running` if another sync is in progress for that area path.
  2. Full ID list fetch (`get_all_ids`) + incremental changed-ID fetch since the stored checkpoint (`get_changed_ids`).
  3. Upserts changed items, then diffs current ADO IDs against stored IDs to delete items that left scope.
  4. Advances the checkpoint to the max `changed_date` seen.
  5. After the checkpoint advances, syncs work item history (`work_item_history`): on an area path's first sync (`history_loaded_at` unset) it backfills every current work item; on later syncs it only fetches history for the delta-changed items. Per-item failures (e.g. `AdoRetryExhaustedError`) are caught and skipped rather than failing the whole sync — a poisoned item must not stall the other items or roll back the checkpoint/upsert/delete work already done. `AdoAuthError` is not caught here and propagates immediately, same as elsewhere. `history_loaded_at` is only set once a full first-load backfill completes with zero item failures; otherwise the next sync retries the full backfill. Commits periodically (`HISTORY_COMMIT_BATCH_SIZE`) during this loop to bound transaction length on large first loads — a deliberate trade-off: an error after a mid-loop commit (e.g. `AdoAuthError` on item 55 after the item-50 commit) leaves that batch's checkpoint/upserts/history durable even though the sync as a whole reports failure. This is safe only because every write in this path is upsert-idempotent; the next successful sync self-heals any gap.
  6. Always releases the lock in `finally`, and on any exception calls `_fail`, which **rolls back first** (a failed `_do_sync` can leave the transaction aborted) before writing the error status — this ordering matters, don't reorder it.
  - First sync for an area path is effectively a full load (no checkpoint yet); later syncs are incremental.
- `scheduler.py` — APScheduler background job ticking every minute; per-area-path due time is `last_sync_at + intervalo_minutos`, computed in Python (not via separate per-row jobs).
- `routes.py` — `create_app(conn_factory=...)` factory pattern; routes open a connection per request via the injectable `conn_factory` (this is how tests substitute a test DB — see `test_routes.py`). Manual sync endpoint returns 409 if a sync is already running.
- `db.py` — schema is defined as one `SCHEMA_SQL` string with `CREATE TABLE IF NOT EXISTS`; new columns are added via appended `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements rather than migration files.

### Schema relationships
`area_paths` (1) → `work_items`, `sync_checkpoints` (1:1), `sync_logs` (1:many), all keyed by `area_path_id`. `raw_json` on `work_items` stores the full ADO API response (all fields, including custom ones) even though only a few columns are projected out for querying. `work_item_history` is keyed by `(work_item_id, rev)` and is **not** FK'd to `work_items` — history rows survive a work item leaving the area path's scope (and being deleted from `work_items`). `area_paths.history_loaded_at` marks whether the one-time full history backfill has completed for that area path; it stays unset until a first-load backfill finishes with zero per-item failures.

### Failure surfacing
Sync failures are stored per-row (`last_sync_status`, `last_error_msg`) rather than raised to the UI as exceptions. `routes.py`'s index view flags `auth_error` specifically so the template can show a banner prompting the user to check `AZURE_DEVOPS_API_KEY`.
```

- [ ] **Step 2: Rewrite root README.md**

Replace the full contents of `README.md` with:

```markdown
# Azure DevOps Sync Monorepo

Enterprise monorepo for syncing Azure DevOps work items into PostgreSQL and
(in future phases) exposing them for read-only consumption.

## Layout

```
apps/
  sync-service/      Flask app — syncs Azure DevOps → PostgreSQL.
                      The ONLY app in this repo authorized to write to
                      the database. See apps/sync-service/README.md.
packages/
  shared-contracts/       (placeholder) DTOs/schemas shared across apps.
  shared-config/          (placeholder) lint/formatter/convention templates.
  shared-observability/   (placeholder) logging/tracing/metrics helpers.
  shared-db-guidelines/   (placeholder) data-access documentation/utilities.
docs/
  architecture/       System-level architecture docs.
  adr/                Architecture Decision Records.
  standards/          Technology lifecycle / governance rules.
```

## Running the sync service

```bash
cd apps/sync-service
pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:5000. See `apps/sync-service/README.md` for env vars
and test setup.

## Roadmap

Today: `apps/sync-service` is the only app, and the only database writer.

Next:
1. `apps/api-read` — read-only backend querying the same database.
2. `apps/web-read` — frontend listing data via `apps/api-read`.
3. Database index review for the new read-heavy access pattern.

Each of the above will land as its own design spec + implementation plan
(see `docs/superpowers/specs/` and `docs/superpowers/plans/`) — this repo is
built incrementally, not as a big-bang rewrite.

## Governance

- Architecture decisions: `docs/adr/`
- Technology lifecycle (semestral review, V-2 annual upgrade rule):
  `docs/standards/technology-lifecycle.md`
- Single-writer rule: `docs/adr/0002-single-writer.md`
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: update root docs for monorepo layout"
```

---

### Task 3: Scaffold packages/ placeholders

**Files:**
- Create: `packages/shared-contracts/README.md`
- Create: `packages/shared-config/README.md`
- Create: `packages/shared-observability/README.md`
- Create: `packages/shared-db-guidelines/README.md`

**Interfaces:**
- Produces: four placeholder directories that future specs (api-read, web-read) can populate — no code, README only.

- [ ] **Step 1: Write packages/shared-contracts/README.md**

```markdown
# shared-contracts

**Status:** placeholder — not yet in use.

Will hold DTOs, schemas, and event/type contracts shared between
`apps/sync-service` (writer) and future read-side apps (`apps/api-read`,
`apps/web-read`), so the read side never has to reverse-engineer the
database schema directly.

Populated when `apps/api-read` is scaffolded (see
`docs/architecture/monorepo-architecture.md`).
```

- [ ] **Step 2: Write packages/shared-config/README.md**

```markdown
# shared-config

**Status:** placeholder — not yet in use.

Will hold shared lint/formatter configuration and repository conventions
(naming, ADR templates, PR templates) so each app doesn't redefine its own.

Populated incrementally as a second app is added to `apps/`.
```

- [ ] **Step 3: Write packages/shared-observability/README.md**

```markdown
# shared-observability

**Status:** placeholder — not yet in use.

Will hold shared logging, tracing, and metrics helpers (e.g. Datadog
integration conventions) so `apps/sync-service` and future apps emit
observability data consistently.

Populated when observability requirements are defined for a second app.
```

- [ ] **Step 4: Write packages/shared-db-guidelines/README.md**

```markdown
# shared-db-guidelines

**Status:** placeholder — not yet in use.

Will hold documentation and (if needed) utilities describing how the
read-only side (`apps/api-read`) is allowed to query the database that
`apps/sync-service` owns and writes — index usage guidance, allowed query
patterns, and the boundary that no read-side code issues write SQL.

Populated alongside `docs/architecture/database-index-review.md` when the
index review spec lands.
```

- [ ] **Step 5: Commit**

```bash
git add packages
git commit -m "docs: scaffold packages/ placeholders for future shared code"
```

---

### Task 4: Write architecture and ADR docs

**Files:**
- Create: `docs/architecture/monorepo-architecture.md`
- Create: `docs/adr/0001-monorepo.md`
- Create: `docs/adr/0002-single-writer.md`
- Create: `docs/standards/technology-lifecycle.md`

**Interfaces:**
- Consumes: nothing (pure documentation), but references the final layout produced by Tasks 1-3, so it must be written after those complete.

- [ ] **Step 1: Write docs/architecture/monorepo-architecture.md**

```markdown
# Monorepo Architecture

## Overview

This repository is structured as an enterprise monorepo under `apps/` and
`packages/`. Today it contains one app, `apps/sync-service`, which is both
the data ingestion pipeline and the only database writer.

## App responsibilities

| App | Responsibility | DB access |
|---|---|---|
| `apps/sync-service` | Poll Azure DevOps, normalize, persist work items/history/checkpoints | **read + write** (only writer) |
| `apps/api-read` (planned) | Serve read-only queries over the same database | read-only |
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
        │  reads (planned)
        ▼
apps/api-read       (read-only query layer, planned)
        │  HTTP (planned)
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
```

- [ ] **Step 2: Write docs/adr/0001-monorepo.md**

```markdown
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
```

- [ ] **Step 3: Write docs/adr/0002-single-writer.md**

```markdown
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
```

- [ ] **Step 4: Write docs/standards/technology-lifecycle.md**

```markdown
# Technology Lifecycle Standard

## Semestral stack review

Every officially adopted technology (see the corporate stack list below)
must be reviewed every 6 months for: continued fit, known vulnerabilities,
support status, and whether a newer major version should be adopted.

Cadence: January and July of each year. Record the review outcome as a
dated entry appended to this file (or a linked ADR if the review results in
a change).

## Annual upgrade rule: V-2

For any technology with major versions, this repository targets the
"current major version minus 2" (V-2) at most, reviewed annually. Example:
if the latest major is V10, this repo should be on V8 or newer within one
year of V10's release. Falling further behind than V-2 requires an ADR
explaining why (e.g. a breaking change not yet absorbed) and a remediation
date.

## Corporate stack baseline (as of 2026-07-15)

- Backend: Java 23+, C# 10+, Python 3.12+
- Frontend: React 19+, Angular 21+
- Mobile: Android 11+, iOS 22+, Flutter 3.27+
- Database: PostgreSQL 16+, MongoDB 7+, SQL Server 2022+
- Test: Cypress, WebdriverIO, k6, Apache JMeter, Appium
- Hot Sites: Acquia, Wix
- Cloud/Observability/Tracking: Azure, Datadog, FullStory, Smartlook, Hotjar
- Code Quality/Security: GitHub, SonarQube, Snyk, Apiiro
- Boards: Azure DevOps

## Applying this to the current repo

- `apps/sync-service` runs Python — track it against the Python 3.12+
  baseline and this repo's own `requirements.txt` pins.
- The database is PostgreSQL — track it against the PostgreSQL 16+
  baseline.
- Future `apps/api-read` and `apps/web-read` must pick their stack from the
  baseline above at scaffold time (see their own design specs).

## Review log

| Date | Reviewer | Outcome |
|---|---|---|
| 2026-07-15 | (initial) | Standard established; no prior review to compare against. |
```

- [ ] **Step 5: Commit**

```bash
git add docs/architecture docs/adr docs/standards
git commit -m "docs: add monorepo architecture, ADRs, and technology lifecycle standard"
```

---

## Self-review notes

- Spec coverage: Task 1 covers spec's "reposicionar app existente"; Task 2
  covers root docs update; Task 3 covers `packages/*` placeholders; Task 4
  covers `docs/architecture`, `docs/adr`, `docs/standards` from the spec.
  `apps/api-read`, `apps/web-read`, and the database index review are
  explicitly out of scope per the approved spec and are not tasked here.
- No placeholders left in doc content — every created file has full prose,
  not "TBD".
- Verified the CLAUDE.md/README.md rewritten content matches the current
  file content 1:1 aside from path changes (confirmed by reading the
  existing files before drafting Task 2).
