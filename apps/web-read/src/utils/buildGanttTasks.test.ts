import { describe, expect, test } from "vitest";
import { buildGanttTasks } from "./buildGanttTasks";
import type { FeatureTreeNode } from "./buildFeatureTree";

function node(overrides: Partial<FeatureTreeNode>): FeatureTreeNode {
  return {
    id: 1,
    title: "Node",
    workItemType: "Solution",
    state: null,
    startDate: null,
    targetDate: null,
    effectiveDate: null,
    children: [],
    ...overrides,
  };
}

describe("buildGanttTasks", () => {
  test("maps a root Solution to a summary task with parent 0", () => {
    const tasks = buildGanttTasks([
      node({ id: 1, title: "Sol A", startDate: "2026-01-01T00:00:00", targetDate: "2026-02-01T00:00:00" }),
    ]);

    expect(tasks).toEqual([
      {
        id: 1,
        text: "#1 Sol A",
        start: new Date("2026-01-01T00:00:00"),
        end: new Date("2026-02-01T00:00:00"),
        type: "summary",
        parent: 0,
        open: false,
        state: null,
      },
    ]);
  });

  test("maps a child Epic/Feature to a task with parent set to its ancestor id", () => {
    const tasks = buildGanttTasks([
      node({
        id: 1, title: "Sol A", startDate: "2026-01-01T00:00:00", targetDate: "2026-03-01T00:00:00",
        children: [
          node({ id: 2, title: "Epic A", startDate: "2026-01-01T00:00:00", targetDate: "2026-02-01T00:00:00" }),
        ],
      }),
    ]);

    const child = tasks.find((t) => t.id === 2)!;
    expect(child.type).toBe("task");
    expect(child.parent).toBe(1);
  });

  test("nests three levels deep with correct parent chain", () => {
    const tasks = buildGanttTasks([
      node({
        id: 1, title: "Sol A", startDate: "2026-01-01T00:00:00", targetDate: "2026-04-01T00:00:00",
        children: [
          node({
            id: 2, title: "Epic A", startDate: "2026-01-01T00:00:00", targetDate: "2026-03-01T00:00:00",
            children: [
              node({ id: 3, title: "Feat A", startDate: "2026-01-01T00:00:00", targetDate: "2026-02-01T00:00:00" }),
            ],
          }),
        ],
      }),
    ]);

    expect(tasks.find((t) => t.id === 3)!.parent).toBe(2);
    expect(tasks.find((t) => t.id === 2)!.parent).toBe(1);
    expect(tasks.find((t) => t.id === 1)!.parent).toBe(0);
  });

  test("omits a node missing startDate", () => {
    const tasks = buildGanttTasks([
      node({ id: 1, startDate: null, targetDate: "2026-02-01T00:00:00" }),
    ]);

    expect(tasks).toEqual([]);
  });

  test("omits a node missing targetDate", () => {
    const tasks = buildGanttTasks([
      node({ id: 1, startDate: "2026-01-01T00:00:00", targetDate: null }),
    ]);

    expect(tasks).toEqual([]);
  });

  test("omits an undated child but keeps a dated parent and dated sibling", () => {
    const tasks = buildGanttTasks([
      node({
        id: 1, startDate: "2026-01-01T00:00:00", targetDate: "2026-03-01T00:00:00",
        children: [
          node({ id: 2, startDate: null, targetDate: null }),
          node({ id: 3, startDate: "2026-01-01T00:00:00", targetDate: "2026-02-01T00:00:00" }),
        ],
      }),
    ]);

    expect(tasks.map((t) => t.id).sort()).toEqual([1, 3]);
  });

  test("passes state through unmodified for later color derivation", () => {
    const tasks = buildGanttTasks([
      node({ id: 1, state: "Active", startDate: "2026-01-01T00:00:00", targetDate: "2026-02-01T00:00:00" }),
    ]);

    expect(tasks[0].state).toBe("Active");
  });

  test("returns an empty array for no input", () => {
    expect(buildGanttTasks([])).toEqual([]);
  });

  test("re-parents a dated grandchild to its nearest dated ancestor when its direct parent is undated", () => {
    const tasks = buildGanttTasks([
      node({
        id: 1, startDate: "2026-01-01T00:00:00", targetDate: "2026-03-01T00:00:00",
        children: [
          node({
            id: 2, startDate: null, targetDate: null,
            children: [
              node({ id: 3, startDate: "2026-01-01T00:00:00", targetDate: "2026-02-01T00:00:00" }),
            ],
          }),
        ],
      }),
    ]);

    expect(tasks.map((t) => t.id).sort()).toEqual([1, 3]);
    expect(tasks.find((t) => t.id === 3)!.parent).toBe(1);
  });
});
