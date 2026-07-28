# Task 5 report — Astryx Capacity & Flow page

## Delivered

- Added typed capacity snapshot contracts in `apps/web-read/src/models/capacity.ts`.
- Added `fetchCapacity(areaPathId, year, quarter)`, using `URLSearchParams`, the
  existing non-OK response convention, and the Task 4 `{ data: ... }` envelope.
- Added the Astryx-only `CapacityFlowPage` with Area Path, year, and quarter
  selectors; loading, API-error, unavailable-forecast, and no-area-path states;
  reliable forecast cards; type/throughput/flow/status tables; and warning banners.
- Added `Capacity & Flow` navigation and rendering to `App.tsx`.
- Added client and page tests for request construction, no snapshot, loading, no
  Area Paths, API errors, warnings, and reliable capacity data.

## TDD evidence

The initial focused test run was red as expected:

```text
TypeError: fetchCapacity is not a function
Failed to resolve import "./CapacityFlowPage"
```

The subsequent implementation was kept to the client/page contract covered by
those tests.

## Verification

Executed from `apps/web-read` with the required Node path prefix:

```text
npm test -- --run CapacityFlowPage apiReadClient
2 test files passed; 8 tests passed

npm run build
tsc -b && vite build
✓ built in 6.97s
```

`npm test -- --run` was also executed for the full frontend suite. It has a
pre-existing failure in `SynchronizationPage.test.tsx`: 9 of 18 tests fail,
while the other 55 tests pass. The same 9 tests fail when that file is run
alone, without the Capacity & Flow tests. They assert obsolete accessible names
such as `Synchronize` and `Loading synchronization settings`, whereas the
current Synchronization page exposes area-specific action names such as
`Synchronize Intake\\Platform`. Task 5 does not modify synchronization files;
the focused Task 5 tests and production build pass.

The Vite build emits its existing large-chunk advisory for the generated bundle;
it does not prevent a successful build.

## Review fix â€” round 1

- Kept the initial `fetchAreaPaths` failure distinct from an empty successful
  response. The page now renders an `Error loading area paths` error Banner
  with the API error message, and only shows `No area paths configured` after a
  successful empty response.
- Gave status-duration rows a composite `id` of work-item type plus status and
  made it the Table `idKey`, so statuses shared across work-item types do not
  collide.
- Added focused page coverage for the initial area-path rejection, current
  period request, quarter and area-path refetches, unreliable snapshots hiding
  all forecast cards, and all 12 monthly throughput columns.

Fresh verification after the fix:

```text
npm test -- --run CapacityFlowPage apiReadClient
2 test files passed; 14 tests passed

npm run build
tsc -b && vite build
âœ“ built in 8.58s
```
