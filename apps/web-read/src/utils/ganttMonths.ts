import type { FeatureTreeItem } from "../models/feature";

export interface GanttMonth {
  key: string;
  label: string;
}

const MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function monthKey(isoDate: string): string {
  return isoDate.slice(0, 7);
}

function monthIndex(key: string): number {
  const [year, month] = key.split("-").map(Number);
  return year * 12 + (month - 1);
}

function keyFromIndex(index: number): string {
  const year = Math.floor(index / 12);
  const month = (index % 12) + 1;
  return `${year}-${String(month).padStart(2, "0")}`;
}

function labelFromKey(key: string): string {
  const [year, month] = key.split("-").map(Number);
  return `${MONTH_LABELS[month - 1]} ${year}`;
}

function datedFeatures(items: FeatureTreeItem[]): FeatureTreeItem[] {
  return items.filter(
    (item): item is FeatureTreeItem & { start_date: string; target_date: string } =>
      item.work_item_type === "Feature" && item.start_date !== null && item.target_date !== null
  );
}

export function buildGanttMonths(items: FeatureTreeItem[]): GanttMonth[] {
  const dated = datedFeatures(items);
  if (dated.length === 0) {
    return [];
  }

  let minIndex = Infinity;
  let maxIndex = -Infinity;
  for (const item of dated) {
    minIndex = Math.min(minIndex, monthIndex(monthKey(item.start_date!)));
    maxIndex = Math.max(maxIndex, monthIndex(monthKey(item.target_date!)));
  }

  const months: GanttMonth[] = [];
  for (let i = minIndex; i <= maxIndex; i++) {
    const key = keyFromIndex(i);
    months.push({ key, label: labelFromKey(key) });
  }
  return months;
}

export function featureCoversMonth(item: FeatureTreeItem, monthKeyToCheck: string): boolean {
  if (item.start_date === null || item.target_date === null) {
    return false;
  }
  const target = monthIndex(monthKeyToCheck);
  const start = monthIndex(monthKey(item.start_date));
  const end = monthIndex(monthKey(item.target_date));
  return target >= start && target <= end;
}

export { datedFeatures };
