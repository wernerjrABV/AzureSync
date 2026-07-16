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
