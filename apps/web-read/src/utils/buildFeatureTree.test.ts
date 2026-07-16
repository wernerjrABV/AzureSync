import { describe, expect, test } from "vitest";
import { buildFeatureTree } from "./buildFeatureTree";
import type { FeatureTreeItem } from "../models/feature";

function item(overrides: Partial<FeatureTreeItem>): FeatureTreeItem {
  return {
    id: 1,
    title: "Item",
    work_item_type: "Feature",
    parent_id: null,
    start_date: null,
    target_date: null,
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
});
