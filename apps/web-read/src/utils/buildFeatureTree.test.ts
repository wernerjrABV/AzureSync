import { describe, expect, test } from "vitest";
import { buildFeatureTree } from "./buildFeatureTree";
import type { FeatureTreeItem } from "../models/feature";

function item(overrides: Partial<FeatureTreeItem>): FeatureTreeItem {
  return {
    id: 1,
    title: "Item",
    work_item_type: "Feature",
    state: null,
    parent_id: null,
    start_date: null,
    target_date: null,
    created_date: null,
    activated_date: null,
    closed_date: null,
    ...overrides,
  };
}

describe("buildFeatureTree", () => {
  test("nests Feature under Epic under Solution", () => {
    const tree = buildFeatureTree([
      item({ id: 1, title: "Sol A", work_item_type: "Solution", parent_id: null }),
      item({ id: 2, title: "Epic A", work_item_type: "Epic", parent_id: 1 }),
      item({ id: 3, title: "Feat A", work_item_type: "Feature", parent_id: 2 }),
    ]);

    expect(tree).toHaveLength(1);
    expect(tree[0].id).toBe(1);
    expect(tree[0].children).toHaveLength(1);
    expect(tree[0].children[0].id).toBe(2);
    expect(tree[0].children[0].children).toHaveLength(1);
    expect(tree[0].children[0].children[0].id).toBe(3);
  });

  test("nests Feature directly under Solution when it has no Epic parent", () => {
    const tree = buildFeatureTree([
      item({ id: 1, title: "Sol A", work_item_type: "Solution", parent_id: null }),
      item({ id: 2, title: "Feat A", work_item_type: "Feature", parent_id: 1 }),
    ]);

    expect(tree[0].children).toHaveLength(1);
    expect(tree[0].children[0].id).toBe(2);
    expect(tree[0].children[0].children).toHaveLength(0);
  });

  test("rolls up start_date as the min and target_date as the max of descendants", () => {
    const tree = buildFeatureTree([
      item({ id: 1, title: "Epic A", work_item_type: "Epic", parent_id: null }),
      item({
        id: 2, title: "Feat A", work_item_type: "Feature", parent_id: 1,
        start_date: "2026-02-01T00:00:00", target_date: "2026-03-01T00:00:00",
      }),
      item({
        id: 3, title: "Feat B", work_item_type: "Feature", parent_id: 1,
        start_date: "2026-01-01T00:00:00", target_date: "2026-02-15T00:00:00",
      }),
    ]);

    expect(tree[0].startDate).toBe("2026-01-01T00:00:00");
    expect(tree[0].targetDate).toBe("2026-03-01T00:00:00");
  });

  test("a parent with no dated descendants has null roll-up dates", () => {
    const tree = buildFeatureTree([
      item({ id: 1, title: "Epic A", work_item_type: "Epic", parent_id: null }),
      item({ id: 2, title: "Feat A", work_item_type: "Feature", parent_id: 1 }),
    ]);

    expect(tree[0].startDate).toBeNull();
    expect(tree[0].targetDate).toBeNull();
  });

  test("falls back to '#id' label when title is null", () => {
    const tree = buildFeatureTree([
      item({ id: 1, title: null, work_item_type: "Solution", parent_id: null }),
    ]);

    expect(tree[0].title).toBe("#1");
  });

  test("drops a Feature with no parent instead of showing it as a root", () => {
    const tree = buildFeatureTree([
      item({ id: 1, title: "Sol A", work_item_type: "Solution", parent_id: null }),
      item({ id: 2, title: "Orphan Feature", work_item_type: "Feature", parent_id: null }),
    ]);

    expect(tree).toHaveLength(1);
    expect(tree[0].id).toBe(1);
  });

  test("drops a Feature whose parent_id points to a work item outside the fetched set", () => {
    const tree = buildFeatureTree([
      item({ id: 1, title: "Orphan Feature", work_item_type: "Feature", parent_id: 999 }),
    ]);

    expect(tree).toHaveLength(0);
  });

  test("effectiveDate falls back start_date -> activated_date -> created_date -> closed_date", () => {
    const tree = buildFeatureTree([
      item({ id: 1, work_item_type: "Solution", start_date: "2026-01-01T00:00:00", activated_date: "2020-01-01T00:00:00" }),
      item({ id: 2, work_item_type: "Solution", activated_date: "2026-02-01T00:00:00", created_date: "2020-01-01T00:00:00" }),
      item({ id: 3, work_item_type: "Solution", created_date: "2026-03-01T00:00:00", closed_date: "2020-01-01T00:00:00" }),
      item({ id: 4, work_item_type: "Solution", closed_date: "2026-04-01T00:00:00" }),
      item({ id: 5, work_item_type: "Solution" }),
    ]);

    const byId = new Map(tree.map((n) => [n.id, n]));
    expect(byId.get(1)!.effectiveDate).toBe("2026-01-01T00:00:00");
    expect(byId.get(2)!.effectiveDate).toBe("2026-02-01T00:00:00");
    expect(byId.get(3)!.effectiveDate).toBe("2026-03-01T00:00:00");
    expect(byId.get(4)!.effectiveDate).toBe("2026-04-01T00:00:00");
    expect(byId.get(5)!.effectiveDate).toBeNull();
  });

  test("sorts children within a parent by effectiveDate, most recent first, undated last", () => {
    const tree = buildFeatureTree([
      item({ id: 1, work_item_type: "Epic" }),
      item({ id: 2, title: "Oldest", work_item_type: "Feature", parent_id: 1, start_date: "2025-01-01T00:00:00" }),
      item({ id: 3, title: "Newest", work_item_type: "Feature", parent_id: 1, start_date: "2026-06-01T00:00:00" }),
      item({ id: 4, title: "Undated", work_item_type: "Feature", parent_id: 1 }),
      item({ id: 5, title: "Middle", work_item_type: "Feature", parent_id: 1, start_date: "2025-12-01T00:00:00" }),
    ]);

    expect(tree[0].children.map((c) => c.title)).toEqual(["Newest", "Middle", "Oldest", "Undated"]);
  });

  test("sorts root-level nodes by effectiveDate, most recent first", () => {
    const tree = buildFeatureTree([
      item({ id: 1, title: "Older Solution", work_item_type: "Solution", start_date: "2025-01-01T00:00:00" }),
      item({ id: 2, title: "Newer Solution", work_item_type: "Solution", start_date: "2026-01-01T00:00:00" }),
    ]);

    expect(tree.map((n) => n.title)).toEqual(["Newer Solution", "Older Solution"]);
  });
});
