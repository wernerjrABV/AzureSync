import { describe, expect, test } from "vitest";
import { buildGanttMonths, featureCoversMonth } from "./ganttMonths";
import type { FeatureTreeItem } from "../models/feature";

function item(overrides: Partial<FeatureTreeItem>): FeatureTreeItem {
  return {
    id: 1,
    title: "Item",
    work_item_type: "Feature",
    parent_id: null,
    start_date: null,
    target_date: null,
    created_date: null,
    activated_date: null,
    closed_date: null,
    ...overrides,
  };
}

describe("buildGanttMonths", () => {
  test("spans from the earliest start month to the latest target month", () => {
    const months = buildGanttMonths([
      item({ id: 1, start_date: "2026-01-15T00:00:00", target_date: "2026-02-10T00:00:00" }),
      item({ id: 2, start_date: "2026-03-01T00:00:00", target_date: "2026-04-30T00:00:00" }),
    ]);

    expect(months.map((m) => m.key)).toEqual(["2026-01", "2026-02", "2026-03", "2026-04"]);
  });

  test("ignores features missing either date", () => {
    const months = buildGanttMonths([
      item({ id: 1, start_date: "2026-01-01T00:00:00", target_date: null }),
      item({ id: 2, start_date: null, target_date: "2026-05-01T00:00:00" }),
    ]);

    expect(months).toEqual([]);
  });

  test("returns an empty array for no input", () => {
    expect(buildGanttMonths([])).toEqual([]);
  });

  test("label formats as 'Mon YYYY'", () => {
    const months = buildGanttMonths([
      item({ id: 1, start_date: "2026-01-15T00:00:00", target_date: "2026-01-20T00:00:00" }),
    ]);

    expect(months).toEqual([{ key: "2026-01", label: "Jan 2026" }]);
  });
});

describe("featureCoversMonth", () => {
  test("true when the month falls inside [start, target]", () => {
    const feature = item({ start_date: "2026-01-15T00:00:00", target_date: "2026-03-05T00:00:00" });
    expect(featureCoversMonth(feature, "2026-01")).toBe(true);
    expect(featureCoversMonth(feature, "2026-02")).toBe(true);
    expect(featureCoversMonth(feature, "2026-03")).toBe(true);
  });

  test("false for months outside the range", () => {
    const feature = item({ start_date: "2026-01-15T00:00:00", target_date: "2026-03-05T00:00:00" });
    expect(featureCoversMonth(feature, "2025-12")).toBe(false);
    expect(featureCoversMonth(feature, "2026-04")).toBe(false);
  });

  test("false when either date is missing", () => {
    const feature = item({ start_date: "2026-01-15T00:00:00", target_date: null });
    expect(featureCoversMonth(feature, "2026-01")).toBe(false);
  });
});
