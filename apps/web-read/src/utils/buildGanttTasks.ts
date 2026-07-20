import type { FeatureTreeNode } from "./buildFeatureTree";

export interface GanttTask {
  id: number;
  text: string;
  description?: string | null;
  start: Date;
  end: Date;
  type: "summary" | "task";
  parent: number | 0;
  open: boolean;
  state: string | null;
  plannedStart: Date | null;
  plannedEnd: Date | null;
  executedStart: Date | null;
  executedEnd: Date | null;
}

function walk(
  node: FeatureTreeNode,
  nearestDatedAncestorId: number | 0,
  isRoot: boolean,
  now: Date,
  out: GanttTask[]
): void {
  const plannedStart = node.startDate !== null ? new Date(node.startDate) : null;
  const plannedEnd = node.targetDate !== null ? new Date(node.targetDate) : null;
  const executedStart = node.executedStartDate !== null ? new Date(node.executedStartDate) : null;
  // Chart-only: an in-progress execution (no closed date yet) is drawn up
  // to "today" so the struck-through bar has a visible extent.
  const executedEnd = node.executedInProgress
    ? now
    : node.executedEndDate !== null
      ? new Date(node.executedEndDate)
      : null;

  const hasPlanned = plannedStart !== null && plannedEnd !== null;
  const hasExecuted = executedStart !== null && executedEnd !== null;

  if (hasPlanned || hasExecuted) {
    const starts = [plannedStart, executedStart].filter((d): d is Date => d !== null);
    const ends = [plannedEnd, executedEnd].filter((d): d is Date => d !== null);
    out.push({
      id: node.id,
      text: `#${node.id} ${node.title}`,
      ...(node.description !== undefined ? { description: node.description } : {}),
      start: new Date(Math.min(...starts.map((d) => d.getTime()))),
      end: new Date(Math.max(...ends.map((d) => d.getTime()))),
      type: isRoot ? "summary" : "task",
      parent: nearestDatedAncestorId,
      open: false,
      state: node.state,
      plannedStart,
      plannedEnd,
      executedStart,
      executedEnd,
    });
  }
  const nextAncestorId = hasPlanned || hasExecuted ? node.id : nearestDatedAncestorId;
  for (const child of node.children) {
    walk(child, nextAncestorId, false, now, out);
  }
}

// Defense in depth: a descendant's rendered bar must never extend past
// its dated ancestor's. buildFeatureTree already rolls planned/executed
// dates up the tree so this should be a no-op in the normal case — this
// clamps the CHILD inward to fit the ancestor (never grows the
// ancestor), so it can't introduce an unfilled gap the way widening the
// ancestor did. Tasks are appended in DFS pre-order, so a parent is
// always processed (and already clamped against its own ancestor)
// before any of its descendants are reached here.
function clampToAncestor(tasks: GanttTask[]): void {
  const byId = new Map(tasks.map((t) => [t.id, t]));
  for (const task of tasks) {
    if (task.parent === 0) continue;
    const parent = byId.get(task.parent);
    if (!parent) continue;
    if (task.start < parent.start) task.start = parent.start;
    if (task.end > parent.end) task.end = parent.end;
  }
}

export function buildGanttTasks(roots: FeatureTreeNode[]): GanttTask[] {
  const now = new Date();
  const out: GanttTask[] = [];
  for (const root of roots) {
    walk(root, 0, true, now, out);
  }
  clampToAncestor(out);
  return out;
}
