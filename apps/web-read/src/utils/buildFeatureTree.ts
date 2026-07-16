import type { FeatureTreeItem } from "../models/feature";

export interface FeatureTreeNode {
  id: number;
  title: string;
  workItemType: string;
  startDate: string | null;
  targetDate: string | null;
  children: FeatureTreeNode[];
}

function minDate(a: string | null, b: string | null): string | null {
  if (a === null) return b;
  if (b === null) return a;
  return a < b ? a : b;
}

function maxDate(a: string | null, b: string | null): string | null {
  if (a === null) return b;
  if (b === null) return a;
  return a > b ? a : b;
}

function rollUp(node: FeatureTreeNode): void {
  for (const child of node.children) {
    rollUp(child);
    node.startDate = minDate(node.startDate, child.startDate);
    node.targetDate = maxDate(node.targetDate, child.targetDate);
  }
}

export function buildFeatureTree(items: FeatureTreeItem[]): FeatureTreeNode[] {
  const nodesById = new Map<number, FeatureTreeNode>();
  for (const item of items) {
    nodesById.set(item.id, {
      id: item.id,
      title: item.title ?? `#${item.id}`,
      workItemType: item.work_item_type ?? "Unknown",
      startDate: item.start_date,
      targetDate: item.target_date,
      children: [],
    });
  }

  const roots: FeatureTreeNode[] = [];
  for (const item of items) {
    const node = nodesById.get(item.id)!;
    const parent = item.parent_id !== null ? nodesById.get(item.parent_id) : undefined;
    if (parent) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }

  for (const root of roots) {
    rollUp(root);
  }

  return roots;
}
