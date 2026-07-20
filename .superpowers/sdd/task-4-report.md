# Task 4 Report: Work Item Details Drawer

## Delivered

- Added row selection to `WorkItemsListPage`; selecting a row opens a right-edge `Dialog` and calls `fetchWorkItemDetails(id)`.
- Added drawer states for loading (`Spinner`), detail failures (`Banner`), and loaded data.
- Rendered all current work-item fields with an em dash fallback for `null`, pretty-printed `raw_json`, and every history revision in the API-returned order with its metadata and payload.
- Added request IDs for detail fetches. Starting another selection or closing the drawer invalidates earlier requests so their completion cannot change the current drawer state.
- Added the minimal real DOM testing setup: jsdom, Testing Library React, jest-dom assertions, and a Vitest jsdom environment.

## Test-Driven Development Evidence

1. Added page behavior tests before the page implementation.
2. The first runnable RED showed `fetchWorkItemDetails` had zero calls and the error banner was absent because rows were not wired to detail loading.
3. Implemented the minimum drawer behavior and confirmed the focused page suite passed.
4. Added the stale-response regression test, temporarily removed the request-ID guard, and confirmed RED: the late response for “Fix login” replaced “Second issue”.
5. Restored the request-ID guard and confirmed the focused suite passed.

## Verification

- `npm test -- src/pages/WorkItemsListPage.test.tsx` — 1 file passed, 3 tests passed.
- `npm test` — 4 files passed, 24 tests passed.
- `npm run build` — TypeScript compilation and Vite production build completed successfully.
- `git diff --check` — no whitespace errors.

## Self-Review

- The production UI uses only Astryx components; no custom stylesheet or inline CSS was added.
- The drawer is controlled by `selectedItemId !== null`, positioned at the right edge with `top: 0`, `right: 0`, `bottom: 0`, and has `DialogHeader` close behavior matching the existing Gantt drawer pattern.
- The tests use real Astryx rendering and mock only the API client boundary. Browser API polyfills are local to the page test for jsdom compatibility.

## Concern

Vite emits its existing generic production-build warning that the generated JavaScript chunk is larger than 500 kB. The build exits successfully; Task 4 does not change bundling strategy.
