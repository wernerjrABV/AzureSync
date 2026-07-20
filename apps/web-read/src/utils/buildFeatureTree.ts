import type { FeatureTreeItem } from "../models/feature";

export interface FeatureTreeNode {
  id: number;
  title: string;
  description?: string | null;
  workItemType: string;
  state: string | null;
  startDate: string | null;
  targetDate: string | null;
  // Rolled-up "Executed date" range — start is activated_date only (no
  // created_date fallback: an item with no activated_date is treated as
  // not started, typically state "New"); end is closed_date.
  // executedInProgress is true when this node or any descendant has
  // started executing but hasn't closed yet, in which case
  // executedEndDate is forced to null.
  executedStartDate: string | null;
  executedEndDate: string | null;
  executedInProgress: boolean;
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
    node.executedStartDate = minDate(node.executedStartDate, child.executedStartDate);
    if (child.executedInProgress) {
      node.executedInProgress = true;
    } else {
      // Roll up the end even when the child has no executedStartDate
      // (e.g. closed without ever being activated) — the end date is
      // still real and must not be dropped from the parent's range.
      node.executedEndDate = maxDate(node.executedEndDate, child.executedEndDate);
    }
  }
  if (node.executedInProgress) {
    node.executedEndDate = null;
  }
}

function computeEffectiveDate(item: FeatureTreeItem): string | null {
  return item.start_date ?? item.activated_date ?? item.created_date ?? item.closed_date;
}

function computeExecutedStartDate(item: FeatureTreeItem): string | null {
  return item.activated_date;
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
    const executedStartDate = computeExecutedStartDate(item);
    nodesById.set(item.id, {
      id: item.id,
      title: item.title ?? `#${item.id}`,
      description: item.description,
      workItemType: item.work_item_type ?? "Unknown",
      state: item.state,
      startDate: item.start_date,
      targetDate: item.target_date,
      executedStartDate,
      executedEndDate: item.closed_date,
      executedInProgress: executedStartDate !== null && item.closed_date === null,
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
