import type { FeatureTreeItem } from "../models/feature";

export interface FeatureTreeNode {
  id: number;
  title: string;
  workItemType: string;
  startDate: string | null;
  targetDate: string | null;
  // The node's own date used for ordering — start_date, falling back to
  // activated_date, then created_date, then closed_date. Unlike
  // startDate/targetDate (which roll up from descendants), this is never
  // rolled up: it reflects when this specific item itself began.
  effectiveDate: string | null;
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

function computeEffectiveDate(item: FeatureTreeItem): string | null {
  return item.start_date ?? item.activated_date ?? item.created_date ?? item.closed_date;
}

// Most recent effectiveDate first; items with no date at all sort last.
function byEffectiveDateDescending(a: FeatureTreeNode, b: FeatureTreeNode): number {
  if (a.effectiveDate === null && b.effectiveDate === null) return 0;
  if (a.effectiveDate === null) return 1;
  if (b.effectiveDate === null) return -1;
  return a.effectiveDate < b.effectiveDate ? 1 : a.effectiveDate > b.effectiveDate ? -1 : 0;
}

function sortByEffectiveDate(node: FeatureTreeNode): void {
  node.children.sort(byEffectiveDateDescending);
  for (const child of node.children) {
    sortByEffectiveDate(child);
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
      effectiveDate: computeEffectiveDate(item),
      children: [],
    });
  }

  const roots: FeatureTreeNode[] = [];
  for (const item of items) {
    const node = nodesById.get(item.id)!;
    const parent = item.parent_id !== null ? nodesById.get(item.parent_id) : undefined;
    if (parent) {
      parent.children.push(node);
    } else if (node.workItemType !== "Feature") {
      // A Feature with no parent has nothing to roll up to and is dropped
      // from the tree rather than shown as a meaningless top-level entry.
      roots.push(node);
    }
  }

  for (const root of roots) {
    rollUp(root);
    sortByEffectiveDate(root);
  }
  roots.sort(byEffectiveDateDescending);

  return roots;
}
