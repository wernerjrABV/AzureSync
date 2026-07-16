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
  state: string | null;
}

export function buildGanttTasks(roots: FeatureTreeNode[]): GanttTask[];
```

- Recursively walks `roots`, skipping (and counting) any node without both dates.
- `text` is `` `#${id} ${title}` `` to match the `TreeList` row label convention.
- `state` is passed through verbatim (`node.state`); SVAR's `ITask` type has a
  `[key: string]: any` index signature, so this rides through unmodified and is read
  back inside `taskTemplate` (see Component section) to pick the bar color — SVAR has
  **no native per-task color field** (confirmed against `types/index.d.ts` in the
  `svar-widgets/react-gantt` repo and `@svar-ui/gantt-store`'s `ITask`), only
  per-`type` theme CSS vars, which is why `state` must travel on the task object for
  a template-level color decision instead.
- `open` defaults to `false` for every row (fully collapsed on first render); confirmed
  via the `GanttReadOnly.jsx` demo pattern that `tasks`/`links`/`scales` are passed
  once and SVAR manages expand/collapse internally — no controlled state needed on our
  side.

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
- Else: render `Text` with the omitted-count note (only if `omittedCount > 0`), then:

```tsx
<Willow>
  <Gantt
    readonly={true}
    tasks={tasks}
    scales={[{ unit: "month", step: 1, format: "%F %Y" }]}
    taskTemplate={GanttBarContent}
  />
</Willow>
```

  `readonly` and the `scales` shape/format string (`%F %Y` = e.g. "July 2026") are
  confirmed from `demos/cases/GanttReadOnly.jsx` and `getting_started` in the
  `svar-widgets/react-gantt` repo — not a guess.

- `GanttBarContent` (colocated in `GanttChart.tsx`, not a separate file — it's a small
  render function, no independent responsibility): a `taskTemplate` implementation
  matching the confirmed signature `function GanttBarContent({ data, onAction })`
  (from `demos/custom/MyTaskContent.jsx`). It renders a single absolutely-positioned
  overlay `div` that fully covers the bar area and carries a state-derived CSS class:

```tsx
function GanttBarContent({ data }: { data: GanttTask }) {
  const variant = stateToBadgeVariant(data.state);
  return <div className={`gantt-bar-fill gantt-bar-fill--${variant}`} />;
}
```

  This overlay is necessary because SVAR only exposes bar color via per-`type` theme
  CSS vars (`--wx-gantt-task-fill-color` / `--wx-gantt-project-fill-color`), not
  per-task — see Theming section.

## Theming

New file: `apps/web-read/src/components/GanttChart.css`, imported once by
`GanttChart.tsx` alongside `@svar-ui/react-gantt/all.css`.

Two distinct pieces, both in `GanttChart.css`, imported once by `GanttChart.tsx`
alongside `@svar-ui/react-gantt/all.css`:

**1. Base theme mapping** (sanctioned exception to the "no custom CSS" rule in
`CLAUDE.md`: SVAR's public theming API *is* CSS custom properties, there's no
React-prop equivalent — overriding them is integration, not ad-hoc styling). Only
needs to set a neutral fallback for the two `type`s we use, since real per-row color
comes from the overlay (below) and fully covers it:

```css
.wx-willow-theme {
  --wx-gantt-project-fill-color: var(--astryx-color-neutral-solid);
  --wx-gantt-task-fill-color: var(--astryx-color-neutral-solid);
}
```

**2. Bar overlay** (positioning-only CSS — an actual small addition beyond variable
mapping, needed because SVAR has no per-task color field; approved explicitly as the
resolution for state-based coloring):

```css
.gantt-bar-fill {
  position: absolute;
  inset: 0;
  border-radius: var(--wx-gantt-bar-border-radius);
}
.gantt-bar-fill--info    { background-color: var(--astryx-color-info-solid); }
.gantt-bar-fill--success { background-color: var(--astryx-color-success-solid); }
.gantt-bar-fill--error   { background-color: var(--astryx-color-error-solid); }
.gantt-bar-fill--neutral { background-color: var(--astryx-color-neutral-solid); }
```

Exact Astryx token variable names (`--astryx-color-*-solid` is a placeholder pattern)
must be confirmed by inspecting the installed `@astryxdesign/theme-neutral` package
during implementation — not verified in this design pass, the package wasn't
resolvable in the current environment. If Astryx tokens turn out not to be exposed as
CSS custom properties at all, fall back to importing the same TS/JS token values
Astryx components consume internally rather than hardcoding hex — flagged as an open
item below, not resolved here.

## Integration

`FeaturesRoadmapPage.tsx`: import and render `<GanttChart roots={tree} />` directly
above `<TreeList items={toTreeItemsWithQuarterSeparators(tree, "root")} .../>`, inside
the existing `{areaPathId !== undefined && !loading && !error && tree.length > 0 && (...)}`
block. No changes to the `TreeList` rendering or its surrounding conditionals.

## Testing

- `buildGanttTasks.test.ts` (new): hierarchy flattening (Solution → Epic → Feature,
  `parent` wiring), omission of nodes missing either date (and correct omitted count),
  `type` assignment (`summary` for roots, `task` otherwise), `state` passed through
  unmodified for later use by `GanttBarContent`.
- No `GanttChart.test.tsx` — no precedent for component-level tests in this app (only
  `.ts` utils are unit-tested; pages/components are verified manually in the browser
  per project convention). Verify in the dev server: chart renders, bars span the
  correct months, colors match `TreeList` badges for the same states, expand/collapse
  works, omitted-count note appears when applicable.
- Delete or update `ganttMonths.test.ts` per the decision above.

## Open items to resolve during implementation (not blocking this spec)

1. Exact Astryx CSS custom property names for `--astryx-color-*-solid` (or equivalent).
2. Whether to delete the now-orphaned `ganttMonths.ts` / `ganttMonths.test.ts`.
3. Exact `taskTemplate` callback prop name (`onAction` per the JSX demo vs `onaction`
   per one type-summary pass) — irrelevant to this plan since the overlay doesn't use
   it, but note it if a later change needs task interactivity.
