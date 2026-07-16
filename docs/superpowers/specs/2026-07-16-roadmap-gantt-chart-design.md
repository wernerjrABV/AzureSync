# Roadmap Gantt chart — design

## Goal

Add a Gantt chart above the existing `TreeList` on `FeaturesRoadmapPage`, visualizing
Solutions (and, on drill-down, their Epics/Features) as time-bound bars, so users get
an at-a-glance timeline in addition to the hierarchical list.

## Why a dedicated library

Astryx has no chart/Gantt primitive. A prior WIP attempt (reverted, uncommitted) built
a crude Gantt using `Table` + `Badge` (one `Badge` per covered month-cell). That's
technically viable and needs zero new dependencies, but was explicitly rejected in
favor of a real Gantt library — the team wants proper continuous bars, drag-free but
visually polished timeline rendering, and room to grow (e.g. dependencies, milestones)
without fighting a table-cell hack.

**Chosen library: `@svar-ui/react-gantt`** (MIT-licensed core), over `React Modern
Gantt` and `Bryntum Gantt`:
- Pure React (no JS-framework wrapper), full TypeScript support, React 19 compatible.
- Customization is a first-class, documented concern (time scales, task bars, grid
  columns) rather than an afterthought.
- More mature/maintained than React Modern Gantt; MIT core avoids Bryntum's commercial
  license.
- Trade-off accepted: its own DOM/CSS needs explicit theming to match Astryx (see below).

Sources consulted:
- https://svar.dev/blog/top-react-gantt-charts/
- https://docs.svar.dev/react/gantt/overview/
- https://docs.svar.dev/react/gantt/guides/styling/
- https://github.com/MikaStiebitz/React-Modern-Gantt

## Non-goals

- No editing (drag-resize, drag-move, add/delete tasks). Read-only rendering only.
- No dependency arrows / critical path.
- No syncing expand/collapse state with the `TreeList` below (explicitly decided
  independent).

## Data mapping

### Scope: which nodes become Gantt rows

Input is `FeatureTreeNode[]` roots (Solutions) as already produced by
`buildFeatureTree` in `FeaturesRoadmapPage.tsx` — same data source as the `TreeList`,
no new API calls.

- Root nodes (Solutions) are Gantt rows of SVAR `type: "summary"`.
- Their children (Epics, and Epics' Features) become nested rows of `type: "task"`,
  only present in the SVAR task list when their parent is expanded (`open: true`) —
  SVAR itself manages visibility of children of a collapsed parent once they're part
  of the task list with a `parent` reference, so the full subtree can be included
  upfront; expand/collapse is native SVAR behavior, not something we implement.
- Every node uses `startDate`/`targetDate` as already computed by `buildFeatureTree`'s
  `rollUp` (min/max of descendants, or the node's own dates if a leaf) — no new
  rollup logic needed.
- Nodes missing `startDate` **or** `targetDate` are omitted from the Gantt task list
  entirely (not shown as an empty row). A count of omitted nodes (at the currently
  visible/expanded depth) is shown as a `Text` note above the chart, mirroring the
  `excludedCount` messaging from the reverted prototype.

### New util: `buildGanttTasks.ts`

`apps/web-read/src/utils/buildGanttTasks.ts`:

```ts
export interface GanttTask {
  id: number;
  text: string;
  start: Date;
  end: Date;
  type: "summary" | "task";
  parent: number | 0;
  open: boolean;
  barCss: string; // "gantt-state-info" | "gantt-state-success" | "gantt-state-error" | "gantt-state-neutral"
}

export function buildGanttTasks(roots: FeatureTreeNode[]): GanttTask[];
```

- Recursively walks `roots`, skipping (and counting) any node without both dates.
- `text` is `` `#${id} ${title}` `` to match the `TreeList` row label convention.
- `barCss` is derived from `stateToBadgeVariant(node.state)` (already exported from
  `buildFeatureTree.ts`), mapped 1:1 to a CSS class name (`gantt-state-<variant>`).
- `open` defaults to `false` for every row (fully collapsed on first render); SVAR's
  own interaction toggles it thereafter — we don't manage this via React state
  ourselves unless SVAR's controlled-mode API turns out to require it (confirm during
  implementation; if SVAR requires a controlled `tasks`/`open` state, lift it into
  `GanttChart` as a `useState`, otherwise let SVAR manage it internally).

### Existing `ganttMonths.ts`

Not used by `buildGanttTasks` — SVAR computes its own timeline range from the tasks
it's given. `ganttMonths.ts` (and its test) stay as-is; they're an orphaned utility
from the reverted table-based prototype. Decide during implementation whether to
delete them (no other caller) or keep for a possible future use — default to deleting
since unused code should not linger, unless SVAR's API ends up needing a precomputed
month range (unlikely).

## Component

New file: `apps/web-read/src/components/GanttChart.tsx`.

```ts
interface GanttChartProps {
  roots: FeatureTreeNode[];
}
```

- Computes `tasks = buildGanttTasks(roots)` and `omittedCount`.
- If `tasks.length === 0`: render Astryx `EmptyState` ("No items with both start and
  target dates to plot").
- Else: render `Text` with the omitted-count note (only if `omittedCount > 0`), then
  the SVAR `<Gantt tasks={tasks} scales={[{ unit: "month", step: 1, format: "MMM yyyy" }]} readonly />`
  (exact prop names for readonly mode and month-scale formatting to be confirmed
  against `docs.svar.dev/react/gantt/samples/` during implementation — the docs
  reference a dedicated "Editor: readonly" demo but the exact prop wasn't visible in
  search results).

## Theming

New file: `apps/web-read/src/components/GanttChart.css`, imported once by
`GanttChart.tsx` alongside `@svar-ui/react-gantt/all.css`.

Maps SVAR's theme CSS custom properties to Astryx's own tokens — no hardcoded hex,
no ad-hoc layout/spacing CSS. This is the one sanctioned exception to the "no custom
CSS" rule in `CLAUDE.md`: SVAR's public theming API *is* CSS custom properties, there
is no React-prop equivalent, so overriding them is integration, not ad-hoc styling.

```css
.wx-willow-theme {
  --wx-gantt-project-color: var(--astryx-color-neutral-solid); /* summary rows, overridden per-row by barCss anyway */
}
.gantt-state-info    { --wx-gantt-task-fill-color: var(--astryx-color-info-solid); }
.gantt-state-success { --wx-gantt-task-fill-color: var(--astryx-color-success-solid); }
.gantt-state-error   { --wx-gantt-task-fill-color: var(--astryx-color-error-solid); }
.gantt-state-neutral { --wx-gantt-task-fill-color: var(--astryx-color-neutral-solid); }
```

Exact Astryx token variable names must be confirmed by inspecting the installed
`@astryxdesign/theme-neutral` package during implementation (not verified in this
design pass — package wasn't resolvable in the current environment). If Astryx tokens
turn out not to be exposed as CSS custom properties at all, fall back to importing the
same TS/JS token values Astryx components consume internally, rather than hardcoding
hex — this would need a short follow-up investigation, flagged here rather than
resolved.

## Integration

`FeaturesRoadmapPage.tsx`: import and render `<GanttChart roots={tree} />` directly
above `<TreeList items={toTreeItemsWithQuarterSeparators(tree, "root")} .../>`, inside
the existing `{areaPathId !== undefined && !loading && !error && tree.length > 0 && (...)}`
block. No changes to the `TreeList` rendering or its surrounding conditionals.

## Testing

- `buildGanttTasks.test.ts` (new): hierarchy flattening (Solution → Epic → Feature,
  `parent` wiring), omission of nodes missing either date (and correct omitted count),
  `type` assignment (`summary` for roots, `task` otherwise), `barCss` derived correctly
  per state via `stateToBadgeVariant`.
- No `GanttChart.test.tsx` — no precedent for component-level tests in this app (only
  `.ts` utils are unit-tested; pages/components are verified manually in the browser
  per project convention). Verify in the dev server: chart renders, bars span the
  correct months, colors match `TreeList` badges for the same states, expand/collapse
  works, omitted-count note appears when applicable.
- Delete or update `ganttMonths.test.ts` per the decision above.

## Open items to resolve during implementation (not blocking this spec)

1. Exact SVAR prop names for readonly mode and month-scale formatting.
2. Whether SVAR needs `open` state controlled from React or manages it internally.
3. Exact Astryx CSS custom property names for `--astryx-color-*-solid` (or equivalent).
4. Whether to delete the now-orphaned `ganttMonths.ts` / `ganttMonths.test.ts`.
