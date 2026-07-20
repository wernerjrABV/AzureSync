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
  barExecutedEnd: Date | null;
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
  const executedEnd = node.executedEndDate !== null ? new Date(node.executedEndDate) : null;
  const barExecutedEnd = node.executedInProgress ? now : executedEnd;

  // A task without a target still needs a visible end for the chart. Prefer
  // the real execution end and use today while it is still open.
  const fallbackEnd = plannedEnd ?? barExecutedEnd ?? now;
  const hasPlanned = plannedStart !== null;
  const hasExecuted = executedStart !== null && barExecutedEnd !== null;

  if (hasPlanned || hasExecuted) {
    const starts = [plannedStart, executedStart].filter((d): d is Date => d !== null);
    const ends = [plannedEnd, barExecutedEnd, fallbackEnd].filter((d): d is Date => d !== null);
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
      barExecutedEnd,
    });
  }
  const nextAncestorId = hasPlanned || hasExecuted ? node.id : nearestDatedAncestorId;
  for (const child of node.children) {
    walk(child, nextAncestorId, false, now, out);
  }
}

// Defense in depth: a summary task must cover every dated descendant. The
// tree normally rolls these dates up, but incomplete hierarchy data can leave
// a child outside its parent's interval. Expand the ancestor instead of
// clamping the child, which would leave the child's target marker past the
// end of the summary bar.
function extendAncestors(tasks: GanttTask[]): void {
  const byId = new Map(tasks.map((t) => [t.id, t]));
  for (const task of tasks) {
    if (task.parent === 0) continue;
    const parent = byId.get(task.parent);
    if (!parent) continue;
    if (task.start < parent.start) {
      parent.start = task.start;
      parent.plannedStart = task.plannedStart ?? parent.plannedStart;
      parent.executedStart = task.executedStart ?? parent.executedStart;
    }
    if (task.end > parent.end) {
      parent.end = task.end;
      parent.plannedEnd = task.plannedEnd ?? parent.plannedEnd;
      parent.executedEnd = task.executedEnd ?? parent.executedEnd;
      parent.barExecutedEnd = task.barExecutedEnd ?? parent.barExecutedEnd;
    }
  }
}

export function buildGanttTasks(roots: FeatureTreeNode[]): GanttTask[] {
  const now = new Date();
  const out: GanttTask[] = [];
  for (const root of roots) {
    walk(root, 0, true, now, out);
  }
  extendAncestors(out);
  return out;
}
