# Roadmap Gantt Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only Gantt chart (via `@svar-ui/react-gantt`) above the `TreeList`
on `FeaturesRoadmapPage`, showing Solutions as summary bars with drill-down into
Epics/Features, colored by work item state.

**Architecture:** A new pure util (`buildGanttTasks.ts`) flattens the existing
`FeatureTreeNode[]` (already produced by `buildFeatureTree`) into SVAR's flat
`{id, parent, type, ...}` task shape. A new component (`GanttChart.tsx`) renders
`<Gantt readonly tasks={...} taskTemplate={GanttBarContent} />` wrapped in SVAR's
`Willow` theme, with a small `GanttChart.css` mapping SVAR's theme CSS vars to Astryx
tokens and adding a state-colored overlay div (since SVAR has no native per-task color
field — confirmed against its type definitions).

**Tech Stack:** React 19, TypeScript, Vitest, `@svar-ui/react-gantt@2.7.1`, Astryx
design system (`@astryxdesign/core`, `@astryxdesign/theme-neutral`).

## Global Constraints

- Never write ad-hoc CSS/inline styles/styled-components when an Astryx component
  covers it (`CLAUDE.md`). The two exceptions in this plan (SVAR theme CSS var mapping,
  and the state-color overlay's positioning CSS) are the sanctioned exception described
  in the spec — SVAR's own theming API is CSS custom properties with no React-prop
  equivalent, and per-task color has no field at all in SVAR's API.
- No hardcoded color hex values anywhere — all colors reference Astryx CSS custom
  properties.
- `readonly={true}` on `<Gantt>` — this chart is view-only, never editable.
- Gantt expand/collapse state is independent of the `TreeList` below — no shared state.
- Spec: `docs/superpowers/specs/2026-07-16-roadmap-gantt-chart-design.md`.

---

### Task 1: `buildGanttTasks` util — flatten the feature tree into SVAR tasks

**Files:**
- Create: `apps/web-read/src/utils/buildGanttTasks.ts`
- Test: `apps/web-read/src/utils/buildGanttTasks.test.ts`

**Interfaces:**
- Consumes: `FeatureTreeNode` from `apps/web-read/src/utils/buildFeatureTree.ts`
  (fields used: `id: number`, `title: string`, `state: string | null`,
  `startDate: string | null`, `targetDate: string | null`, `children: FeatureTreeNode[]`).
- Produces:
  ```ts
  export interface GanttTask {
    id: number;
    text: string;
    start: Date;
    end: Date;
    type: "summary" | "task";
    parent: number | 0;
    open: boolean;
    state: string | null;
  }
  export function buildGanttTasks(roots: FeatureTreeNode[]): GanttTask[]
  ```
  Later tasks (`GanttChart.tsx`) import `GanttTask` and `buildGanttTasks` from this
  file.

- [ ] **Step 1: Write the failing tests**

Create `apps/web-read/src/utils/buildGanttTasks.test.ts`:

```ts
import { describe, expect, test } from "vitest";
import { buildGanttTasks } from "./buildGanttTasks";
import type { FeatureTreeNode } from "./buildFeatureTree";

function node(overrides: Partial<FeatureTreeNode>): FeatureTreeNode {
  return {
    id: 1,
    title: "Node",
    workItemType: "Solution",
    state: null,
    startDate: null,
    targetDate: null,
    effectiveDate: null,
    children: [],
    ...overrides,
  };
}

describe("buildGanttTasks", () => {
  test("maps a root Solution to a summary task with parent 0", () => {
    const tasks = buildGanttTasks([
      node({ id: 1, title: "Sol A", startDate: "2026-01-01T00:00:00", targetDate: "2026-02-01T00:00:00" }),
    ]);

    expect(tasks).toEqual([
      {
        id: 1,
        text: "#1 Sol A",
        start: new Date("2026-01-01T00:00:00"),
        end: new Date("2026-02-01T00:00:00"),
        type: "summary",
        parent: 0,
        open: false,
        state: null,
      },
    ]);
  });

  test("maps a child Epic/Feature to a task with parent set to its ancestor id", () => {
    const tasks = buildGanttTasks([
      node({
        id: 1, title: "Sol A", startDate: "2026-01-01T00:00:00", targetDate: "2026-03-01T00:00:00",
        children: [
          node({ id: 2, title: "Epic A", startDate: "2026-01-01T00:00:00", targetDate: "2026-02-01T00:00:00", parent_id: undefined as never }),
        ],
      }),
    ]);

    const child = tasks.find((t) => t.id === 2)!;
    expect(child.type).toBe("task");
    expect(child.parent).toBe(1);
  });

  test("nests three levels deep with correct parent chain", () => {
    const tasks = buildGanttTasks([
      node({
        id: 1, title: "Sol A", startDate: "2026-01-01T00:00:00", targetDate: "2026-04-01T00:00:00",
        children: [
          node({
            id: 2, title: "Epic A", startDate: "2026-01-01T00:00:00", targetDate: "2026-03-01T00:00:00",
            children: [
              node({ id: 3, title: "Feat A", startDate: "2026-01-01T00:00:00", targetDate: "2026-02-01T00:00:00" }),
            ],
          }),
        ],
      }),
    ]);

    expect(tasks.find((t) => t.id === 3)!.parent).toBe(2);
    expect(tasks.find((t) => t.id === 2)!.parent).toBe(1);
    expect(tasks.find((t) => t.id === 1)!.parent).toBe(0);
  });

  test("omits a node missing startDate", () => {
    const tasks = buildGanttTasks([
      node({ id: 1, startDate: null, targetDate: "2026-02-01T00:00:00" }),
    ]);

    expect(tasks).toEqual([]);
  });

  test("omits a node missing targetDate", () => {
    const tasks = buildGanttTasks([
      node({ id: 1, startDate: "2026-01-01T00:00:00", targetDate: null }),
    ]);

    expect(tasks).toEqual([]);
  });

  test("omits an undated child but keeps a dated parent and dated sibling", () => {
    const tasks = buildGanttTasks([
      node({
        id: 1, startDate: "2026-01-01T00:00:00", targetDate: "2026-03-01T00:00:00",
        children: [
          node({ id: 2, startDate: null, targetDate: null }),
          node({ id: 3, startDate: "2026-01-01T00:00:00", targetDate: "2026-02-01T00:00:00" }),
        ],
      }),
    ]);

    expect(tasks.map((t) => t.id).sort()).toEqual([1, 3]);
  });

  test("passes state through unmodified for later color derivation", () => {
    const tasks = buildGanttTasks([
      node({ id: 1, state: "Active", startDate: "2026-01-01T00:00:00", targetDate: "2026-02-01T00:00:00" }),
    ]);

    expect(tasks[0].state).toBe("Active");
  });

  test("returns an empty array for no input", () => {
    expect(buildGanttTasks([])).toEqual([]);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/web-read && npx vitest run buildGanttTasks`
Expected: FAIL — `Cannot find module './buildGanttTasks'` (file doesn't exist yet).

- [ ] **Step 3: Implement `buildGanttTasks.ts`**

Create `apps/web-read/src/utils/buildGanttTasks.ts`:

```ts
import type { FeatureTreeNode } from "./buildFeatureTree";

export interface GanttTask {
  id: number;
  text: string;
  start: Date;
  end: Date;
  type: "summary" | "task";
  parent: number | 0;
  open: boolean;
  state: string | null;
}

function walk(node: FeatureTreeNode, parent: number | 0, isRoot: boolean, out: GanttTask[]): void {
  if (node.startDate !== null && node.targetDate !== null) {
    out.push({
      id: node.id,
      text: `#${node.id} ${node.title}`,
      start: new Date(node.startDate),
      end: new Date(node.targetDate),
      type: isRoot ? "summary" : "task",
      parent,
      open: false,
      state: node.state,
    });
  }
  for (const child of node.children) {
    walk(child, node.id, false, out);
  }
}

export function buildGanttTasks(roots: FeatureTreeNode[]): GanttTask[] {
  const out: GanttTask[] = [];
  for (const root of roots) {
    walk(root, 0, true, out);
  }
  return out;
}
```

Note: a node whose dates are missing is skipped as a task, but its children are still
walked (with `parent` pointing at that skipped node's id via the `node.id` passed down
regardless of whether it was pushed) — per the spec, omission only affects whether a
row is drawn, not tree traversal. Since SVAR requires a task's `parent` to reference an
existing task id, and an omitted node is never pushed, this would produce a dangling
`parent` reference for grandchildren of an omitted node. Given the test above only
covers a direct undated child (not an undated child with its own dated children), add
one more test before considering this task done:

- [ ] **Step 3b: Write a test for a dated grandchild under an undated child**

Add to `buildGanttTasks.test.ts`:

```ts
  test("re-parents a dated grandchild to its nearest dated ancestor when its direct parent is undated", () => {
    const tasks = buildGanttTasks([
      node({
        id: 1, startDate: "2026-01-01T00:00:00", targetDate: "2026-03-01T00:00:00",
        children: [
          node({
            id: 2, startDate: null, targetDate: null,
            children: [
              node({ id: 3, startDate: "2026-01-01T00:00:00", targetDate: "2026-02-01T00:00:00" }),
            ],
          }),
        ],
      }),
    ]);

    expect(tasks.map((t) => t.id).sort()).toEqual([1, 3]);
    expect(tasks.find((t) => t.id === 3)!.parent).toBe(1);
  });
```

- [ ] **Step 3c: Run this test, confirm it fails against the Step 3 implementation**

Run: `cd apps/web-read && npx vitest run buildGanttTasks`
Expected: FAIL on the re-parenting test — `parent` is `2` (the omitted node's id, which
never became a task), not `1`.

- [ ] **Step 3d: Fix `walk` to re-parent through omitted nodes**

Replace the implementation in `apps/web-read/src/utils/buildGanttTasks.ts`:

```ts
import type { FeatureTreeNode } from "./buildFeatureTree";

export interface GanttTask {
  id: number;
  text: string;
  start: Date;
  end: Date;
  type: "summary" | "task";
  parent: number | 0;
  open: boolean;
  state: string | null;
}

function walk(
  node: FeatureTreeNode,
  nearestDatedAncestorId: number | 0,
  isRoot: boolean,
  out: GanttTask[]
): void {
  const hasDates = node.startDate !== null && node.targetDate !== null;
  if (hasDates) {
    out.push({
      id: node.id,
      text: `#${node.id} ${node.title}`,
      start: new Date(node.startDate!),
      end: new Date(node.targetDate!),
      type: isRoot ? "summary" : "task",
      parent: nearestDatedAncestorId,
      open: false,
      state: node.state,
    });
  }
  const nextAncestorId = hasDates ? node.id : nearestDatedAncestorId;
  for (const child of node.children) {
    walk(child, nextAncestorId, false, out);
  }
}

export function buildGanttTasks(roots: FeatureTreeNode[]): GanttTask[] {
  const out: GanttTask[] = [];
  for (const root of roots) {
    walk(root, 0, true, out);
  }
  return out;
}
```

- [ ] **Step 4: Run all tests in this file and confirm they pass**

Run: `cd apps/web-read && npx vitest run buildGanttTasks`
Expected: PASS — all 9 tests green.

- [ ] **Step 5: Commit**

```bash
git add apps/web-read/src/utils/buildGanttTasks.ts apps/web-read/src/utils/buildGanttTasks.test.ts
git commit -m "feat(web-read): add buildGanttTasks util to flatten feature tree for Gantt"
```

---

### Task 2: Add `@svar-ui/react-gantt` dependency

**Files:**
- Modify: `apps/web-read/package.json`

**Interfaces:**
- Consumes: nothing.
- Produces: `@svar-ui/react-gantt` importable as `import { Gantt, Willow } from "@svar-ui/react-gantt"` and `import "@svar-ui/react-gantt/all.css"` in Task 3.

- [ ] **Step 1: Add the dependency**

Run:
```bash
cd apps/web-read && npm install @svar-ui/react-gantt@2.7.1
```

- [ ] **Step 2: Verify it installed and the app still type-checks**

Run: `cd apps/web-read && npx tsc -b --noEmit`
Expected: no new errors (the import isn't used yet, so this just confirms `npm install`
didn't break the existing build).

- [ ] **Step 3: Commit**

```bash
git add apps/web-read/package.json apps/web-read/package-lock.json
git commit -m "chore(web-read): add @svar-ui/react-gantt dependency"
```

---

### Task 3: `GanttChart` component

**Files:**
- Create: `apps/web-read/src/components/GanttChart.tsx`
- Create: `apps/web-read/src/components/GanttChart.css`

**Interfaces:**
- Consumes:
  - `GanttTask`, `buildGanttTasks` from `apps/web-read/src/utils/buildGanttTasks.ts` (Task 1)
  - `FeatureTreeNode`, `stateToBadgeVariant` from `apps/web-read/src/utils/buildFeatureTree.ts`
  - `@svar-ui/react-gantt`'s `Gantt`, `Willow` (Task 2)
  - Astryx `EmptyState` (`@astryxdesign/core/EmptyState`), `Text` (`@astryxdesign/core/Text`)
- Produces: `export default function GanttChart(props: { roots: FeatureTreeNode[] }): JSX.Element`, consumed by `FeaturesRoadmapPage.tsx` in Task 4.

- [ ] **Step 1: Create `GanttChart.css`**

The real Astryx color custom properties were confirmed by reading
`node_modules/@astryxdesign/theme-neutral/dist/theme.css` directly (there is no
`--astryx-color-*` naming — actual prefix is `--color-`). `Badge`'s semantic variants
(`info`/`success`/`error`) render via hardcoded hex in that package, not reusable
custom properties, but the non-semantic family tokens are real, stable custom
properties also used elsewhere in the theme (e.g. `.astryx-banner.info` maps to the
"blue" family): `--color-background-blue` (info), `--color-background-green`
(success), `--color-background-red` (error), `--color-background-gray` (neutral).
Use these exact names — do not use `--astryx-color-*`, it doesn't exist.

Create `apps/web-read/src/components/GanttChart.css`:

```css
.wx-willow-theme {
  --wx-gantt-project-fill-color: var(--color-background-gray);
  --wx-gantt-task-fill-color: var(--color-background-gray);
}

.gantt-bar-fill {
  position: absolute;
  inset: 0;
  border-radius: var(--wx-gantt-bar-border-radius);
}
.gantt-bar-fill--info { background-color: var(--color-background-blue); }
.gantt-bar-fill--success { background-color: var(--color-background-green); }
.gantt-bar-fill--error { background-color: var(--color-background-red); }
.gantt-bar-fill--neutral { background-color: var(--color-background-gray); }
```

- [ ] **Step 2: Create `GanttChart.tsx`**

Create `apps/web-read/src/components/GanttChart.tsx`:

```tsx
import { Gantt, Willow } from "@svar-ui/react-gantt";
import "@svar-ui/react-gantt/all.css";
import "./GanttChart.css";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Text } from "@astryxdesign/core/Text";
import { buildGanttTasks, type GanttTask } from "../utils/buildGanttTasks";
import { stateToBadgeVariant, type FeatureTreeNode } from "../utils/buildFeatureTree";

function countAllNodes(roots: FeatureTreeNode[]): number {
  let count = 0;
  const stack = [...roots];
  while (stack.length > 0) {
    const n = stack.pop()!;
    count += 1;
    stack.push(...n.children);
  }
  return count;
}

function GanttBarContent({ data }: { data: GanttTask }) {
  const variant = stateToBadgeVariant(data.state);
  return <div className={`gantt-bar-fill gantt-bar-fill--${variant}`} />;
}

export interface GanttChartProps {
  roots: FeatureTreeNode[];
}

export default function GanttChart({ roots }: GanttChartProps) {
  const tasks = buildGanttTasks(roots);
  const omittedCount = countAllNodes(roots) - tasks.length;

  if (tasks.length === 0) {
    return (
      <EmptyState
        title="No items with dates to plot"
        description="The Gantt chart needs at least one Solution, Epic, or Feature with both a start and target date."
      />
    );
  }

  return (
    <>
      {omittedCount > 0 && (
        <Text>
          {omittedCount} item(s) hidden from the Gantt chart for missing start or target date.
        </Text>
      )}
      <Willow>
        <Gantt
          readonly={true}
          tasks={tasks}
          scales={[{ unit: "month", step: 1, format: "%F %Y" }]}
          taskTemplate={GanttBarContent}
        />
      </Willow>
    </>
  );
}
```

- [ ] **Step 3: Type-check**

Run: `cd apps/web-read && npx tsc -b --noEmit`
Expected: no errors. If `taskTemplate`'s expected prop type doesn't structurally match
`{ data: GanttTask }` (SVAR's `ITask` has more optional fields than `GanttTask`), adjust
`GanttBarContent`'s parameter type to `{ data: import("@svar-ui/react-gantt").ITask }` and
read `data.state` (relying on `ITask`'s `[key: string]: any` index signature) instead —
resolve whichever way `tsc` reports, don't leave a type error unresolved.

- [ ] **Step 4: Commit**

```bash
git add apps/web-read/src/components/GanttChart.tsx apps/web-read/src/components/GanttChart.css
git commit -m "feat(web-read): add GanttChart component wrapping SVAR React Gantt"
```

---

### Task 4: Integrate into `FeaturesRoadmapPage` and resolve the orphaned `ganttMonths` util

**Files:**
- Modify: `apps/web-read/src/pages/FeaturesRoadmapPage.tsx`
- Delete: `apps/web-read/src/utils/ganttMonths.ts`
- Delete: `apps/web-read/src/utils/ganttMonths.test.ts`

**Interfaces:**
- Consumes: `GanttChart` default export from `apps/web-read/src/components/GanttChart.tsx` (Task 3).
- Produces: nothing consumed further (this is the integration point).

- [ ] **Step 1: Delete the orphaned `ganttMonths` util and its test**

These were built for the reverted Table-based Gantt prototype and have no other
caller now that `buildGanttTasks` (Task 1) computes the timeline range via SVAR
directly.

```bash
git rm apps/web-read/src/utils/ganttMonths.ts apps/web-read/src/utils/ganttMonths.test.ts
```

- [ ] **Step 2: Add the `GanttChart` import and render it above `TreeList`**

In `apps/web-read/src/pages/FeaturesRoadmapPage.tsx`, add the import alongside the
other local imports (after the `TreeList` import at line 9):

```tsx
import GanttChart from "../components/GanttChart";
```

Then change the render block (currently lines 129–131):

```tsx
      {areaPathId !== undefined && !loading && !error && tree.length > 0 && (
        <TreeList items={toTreeItemsWithQuarterSeparators(tree, "root")} density="balanced" />
      )}
```

to:

```tsx
      {areaPathId !== undefined && !loading && !error && tree.length > 0 && (
        <>
          <GanttChart roots={tree} />
          <TreeList items={toTreeItemsWithQuarterSeparators(tree, "root")} density="balanced" />
        </>
      )}
```

- [ ] **Step 3: Type-check and run the full test suite**

Run: `cd apps/web-read && npx tsc -b --noEmit && npx vitest run`
Expected: no type errors; all tests pass (the `ganttMonths.test.ts` suite is gone, all
remaining suites — including the new `buildGanttTasks.test.ts` — pass).

- [ ] **Step 4: Commit**

```bash
git add apps/web-read/src/pages/FeaturesRoadmapPage.tsx
git commit -m "feat(web-read): render GanttChart above the features roadmap TreeList"
```

---

### Task 5: Manual verification in the browser

**Files:** none (verification only).

**Interfaces:** none.

- [ ] **Step 1: Start the dev server**

Run: `cd apps/web-read && npm run dev`

- [ ] **Step 2: Open the Features Roadmap page and verify**

Navigate to the Features Roadmap page (select an area path with at least one
Solution/Epic/Feature that has both start and target dates set). Confirm:
- The Gantt chart renders above the `TreeList`, with one collapsed summary bar per
  Solution.
- Bar colors match the `Badge` colors shown in the `TreeList` for the same `state`
  (info/success/error/neutral) — not SVAR's default blue/green.
- Expanding a Solution row (native SVAR chevron/click) reveals its Epic/Feature rows
  with correctly nested date ranges, still colored by their own state.
- If any Solution/Epic/Feature lacks a start or target date, it's absent from the
  chart, and the "N item(s) hidden…" text appears above the chart with the correct
  count.
- If the selected area path has zero dated items, the `EmptyState` message renders
  instead of an empty chart.
- No visual clash with Astryx (fonts, spacing, borders look consistent with the rest
  of the page) — if something looks off, note it specifically (don't just say "looks
  fine") since this is view-only verification, not a test suite.

- [ ] **Step 3: Report findings**

If everything matches, no further action. If anything doesn't match, capture the
specific discrepancy (a screenshot description or exact visual detail) before deciding
whether it needs a follow-up task — do not silently patch CSS without understanding
why the mismatch happened.
