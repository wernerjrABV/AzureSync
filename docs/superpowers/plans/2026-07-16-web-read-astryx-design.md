# web-read Astryx Design System Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `apps/web-read` render its single work-items page using only native `@astryxdesign/core` components under the `@astryxdesign/theme-neutral` theme, with a reorganized AppShell/TopNav layout, and zero custom CSS.

**Architecture:** Add the three Astryx packages, wire up theme CSS imports in a new `src/index.css`, wrap the app shell (`App.tsx`) in `AppShell` + `TopNav`, and rewrite `WorkItemsListPage.tsx` to use `Selector`, `TextInput`, `Table`, `Pagination`, `Banner`, `EmptyState`, and `Spinner` instead of raw HTML elements.

**Tech Stack:** React 19, Vite 6, TypeScript 5.7, `@astryxdesign/core` 0.1.6, `@astryxdesign/theme-neutral`, `@astryxdesign/cli` (dev-only tooling, not imported in runtime code).

## Global Constraints

- No custom CSS files/classes beyond the three `@import` lines needed to load Astryx's reset/core/theme stylesheets (spec: "Setup de tema").
- Do not modify `apiReadClient.ts`, `models/areaPath.ts`, `models/workItem.ts`, or the `apps/api-read` contract (spec: "Fora de escopo").
- Do not add sideNav, multi-page navigation, dark mode toggle, or breadcrumbs (spec: "Fora de escopo").
- Do not introduce a test runner/suite — `apps/web-read` has none today and the spec explicitly scopes verification to manual dev-server checks (spec: "Testes").
- Use `theme-neutral` tokens as-is; no color/token overrides (spec: "Fora de escopo").
- Table column `state` renders via `Badge` using the component's default (`neutral`) variant — no invented color semantics for Azure DevOps states (spec: "Mapeamento de estado → componente").

---

### Task 1: Install Astryx packages and wire up theme CSS

**Files:**
- Modify: `apps/web-read/package.json`
- Create: `apps/web-read/src/index.css`
- Modify: `apps/web-read/src/main.tsx`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: theme CSS loaded globally before any component renders. Later tasks import components from `@astryxdesign/core/*` and rely on the theme being active (e.g. `Button`, `Table`, `AppShell` render with `theme-neutral` tokens applied).

- [ ] **Step 1: Install the packages as real dependencies**

Run from `apps/web-read`:

```bash
npm install @astryxdesign/core@0.1.6 @astryxdesign/theme-neutral@0.1.6
npm install --save-dev @astryxdesign/cli@0.1.6
```

Expected: `package.json` `dependencies` gains `@astryxdesign/core` and `@astryxdesign/theme-neutral`; `devDependencies` gains `@astryxdesign/cli`.

- [ ] **Step 2: Create the global theme stylesheet**

Create `apps/web-read/src/index.css`:

```css
@import '@astryxdesign/core/reset.css';
@import '@astryxdesign/core/astryx.css';
@import '@astryxdesign/theme-neutral/theme.css';
```

- [ ] **Step 3: Import the stylesheet in the app entry point**

Modify `apps/web-read/src/main.tsx` — add the CSS import as the first line:

```tsx
import "./index.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

- [ ] **Step 4: Verify the app still builds and loads with the theme active**

Run: `cd apps/web-read && npm run dev`
Expected: Vite starts without errors. Open the printed local URL in a browser — the page still renders the old raw-HTML UI (unchanged so far), but with no console errors about missing CSS imports. Stop the dev server (Ctrl+C) once confirmed.

- [ ] **Step 5: Commit**

```bash
git add apps/web-read/package.json apps/web-read/package-lock.json apps/web-read/src/index.css apps/web-read/src/main.tsx
git commit -m "chore(web-read): install Astryx design system and load neutral theme CSS"
```

---

### Task 2: Wrap the app in AppShell + TopNav

**Files:**
- Modify: `apps/web-read/src/App.tsx`

**Interfaces:**
- Consumes: `AppShell`, `TopNav`, `TopNavHeading` from `@astryxdesign/core/AppShell` and `@astryxdesign/core/TopNav` (installed in Task 1).
- Produces: `App` renders `<WorkItemsListPage />` as the sole child of `AppShell`'s content area. Task 3 does not need to change how `WorkItemsListPage` is mounted — it continues to be a plain child component with no props.

- [ ] **Step 1: Rewrite App.tsx to use AppShell and TopNav**

Replace the full contents of `apps/web-read/src/App.tsx`:

```tsx
import { AppShell } from "@astryxdesign/core/AppShell";
import { TopNav } from "@astryxdesign/core/TopNav";
import { TopNavHeading } from "@astryxdesign/core/TopNav";
import WorkItemsListPage from "./pages/WorkItemsListPage";

export default function App() {
  return (
    <AppShell
      variant="elevated"
      contentPadding={4}
      topNav={
        <TopNav
          label="Main navigation"
          heading={<TopNavHeading heading="Work Items" />}
        />
      }
    >
      <WorkItemsListPage />
    </AppShell>
  );
}
```

- [ ] **Step 2: Verify it renders without errors**

Run: `cd apps/web-read && npm run dev`
Expected: Page loads with a top nav bar showing "Work Items" as the heading, and the (still raw-HTML) work items page rendered below it inside the shell's content area, with theme-neutral background/spacing visibly applied to the shell itself. No console errors. Stop the dev server.

- [ ] **Step 3: Commit**

```bash
git add apps/web-read/src/App.tsx
git commit -m "feat(web-read): wrap app in Astryx AppShell and TopNav"
```

---

### Task 3: Rewrite WorkItemsListPage with Astryx components

**Files:**
- Modify: `apps/web-read/src/pages/WorkItemsListPage.tsx`

**Interfaces:**
- Consumes: `fetchWorkItems`, `fetchAreaPaths` from `../services/apiReadClient` (unchanged signatures); `WorkItem` from `../models/workItem`; `AreaPath` from `../models/areaPath`; `Card`, `HStack` from `@astryxdesign/core/Layout`; `Selector` from `@astryxdesign/core/Selector`; `TextInput` from `@astryxdesign/core/TextInput`; `Table`, `proportional`, `pixel` from `@astryxdesign/core/Table`; `Pagination` from `@astryxdesign/core/Pagination`; `Banner` from `@astryxdesign/core/Banner`; `EmptyState` from `@astryxdesign/core/EmptyState`; `Spinner` from `@astryxdesign/core/Spinner`; `Badge` from `@astryxdesign/core/Badge`.
- Produces: default-exported `WorkItemsListPage` component with the same external contract as before (no props, self-contained data fetching) — nothing downstream depends on its internals.

- [ ] **Step 1: Replace the full contents of WorkItemsListPage.tsx**

```tsx
import { useEffect, useState } from "react";
import { Card } from "@astryxdesign/core/Layout";
import { HStack } from "@astryxdesign/core/Layout";
import { Selector } from "@astryxdesign/core/Selector";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Table, proportional, pixel } from "@astryxdesign/core/Table";
import { Pagination } from "@astryxdesign/core/Pagination";
import { Banner } from "@astryxdesign/core/Banner";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Badge } from "@astryxdesign/core/Badge";
import { fetchWorkItems, fetchAreaPaths } from "../services/apiReadClient";
import type { WorkItem } from "../models/workItem";
import type { AreaPath } from "../models/areaPath";

const PAGE_SIZE = 50;

export default function WorkItemsListPage() {
  const [areaPaths, setAreaPaths] = useState<AreaPath[]>([]);
  const [items, setItems] = useState<WorkItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [areaPathId, setAreaPathId] = useState<number | undefined>(undefined);
  const [workItemType, setWorkItemType] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAreaPaths()
      .then(setAreaPaths)
      .catch(() => {
        /* area path filter is optional; a failure here just leaves the dropdown empty */
      });
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchWorkItems({
      areaPathId,
      workItemType: workItemType || undefined,
      page,
      pageSize: PAGE_SIZE,
    })
      .then((response) => {
        setItems(response.data);
        setTotal(response.pagination.total);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [areaPathId, workItemType, page]);

  return (
    <Card>
      <HStack gap={4} align="end" wrap="wrap">
        <Selector
          label="Area path"
          hasSearch
          hasClear
          value={areaPathId !== undefined ? String(areaPathId) : null}
          onChange={(value) => {
            setPage(1);
            setAreaPathId(value ? Number(value) : undefined);
          }}
          options={areaPaths.map((ap) => ({
            value: String(ap.id),
            label: ap.area_path,
          }))}
          placeholder="All"
          width={280}
        />
        <TextInput
          label="Type"
          hasClear
          value={workItemType}
          onChange={(value) => {
            setPage(1);
            setWorkItemType(value);
          }}
          placeholder="e.g. Bug"
          width={200}
        />
      </HStack>

      {error && (
        <Banner status="error" title="Error loading work items" description={error} />
      )}

      {loading && !error && <Spinner label="Loading work items" />}

      {!loading && !error && items.length === 0 && (
        <EmptyState
          title="No work items found"
          description="Try adjusting the area path or type filter."
        />
      )}

      {!loading && !error && items.length > 0 && (
        <>
          <Table
            data={items}
            idKey="id"
            density="balanced"
            dividers="rows"
            hasHover
            columns={[
              { key: "id", header: "ID", width: pixel(80) },
              { key: "title", header: "Title", width: proportional(3) },
              { key: "work_item_type", header: "Type", width: proportional(1) },
              {
                key: "state",
                header: "State",
                width: proportional(1),
                renderCell: (item) => <Badge label={item.state ?? "—"} />,
              },
              { key: "assigned_to", header: "Assigned To", width: proportional(1) },
              { key: "changed_date", header: "Changed Date", width: proportional(1) },
            ]}
          />

          <Pagination
            variant="compact"
            page={page}
            onChange={setPage}
            totalItems={total}
            pageSize={PAGE_SIZE}
          />
        </>
      )}
    </Card>
  );
}
```

- [ ] **Step 2: Type-check the project**

Run: `cd apps/web-read && npx tsc -b --noEmit`
Expected: no errors. If `Badge`'s `label` prop rejects `item.state ?? "—"` due to `state: string | null` narrowing, the `?? "—"` already coerces to `string`, so this should type-check cleanly.

- [ ] **Step 3: Manually verify the full page in the browser**

Run: `cd apps/web-read && npm run dev` (ensure `apps/api-read` is also running per its own README so the page has real data)

Check each of:
- Initial load shows a `Spinner`, then the `Table` with data once loaded.
- Selecting an area path in the `Selector` filters the table (page resets to 1).
- Clearing the area path (via the clear button) goes back to "All".
- Typing a work item type in the `TextInput` filters the table (page resets to 1).
- `Pagination` "compact" controls move between pages and the count matches `total`.
- Setting a type filter that matches nothing shows the `EmptyState`.
- Stopping `apps/api-read` and reloading shows the `Banner` with the error message.

Stop the dev server once all checks pass.

- [ ] **Step 4: Commit**

```bash
git add apps/web-read/src/pages/WorkItemsListPage.tsx
git commit -m "feat(web-read): migrate work items page to Astryx components"
```
