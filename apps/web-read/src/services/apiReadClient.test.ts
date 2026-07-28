import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchCapacity, fetchWorkItemDetails } from "./apiReadClient";

describe("fetchWorkItemDetails", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("fetches and parses the work item details response", async () => {
    const details = {
      item: {
        id: 42,
        area_path_id: 7,
        title: "Fix login",
        work_item_type: "Bug",
        state: "Active",
        assigned_to: null,
        changed_date: "2026-07-20T10:00:00",
        parent_id: null,
        raw_json: { fields: { "System.Title": "Fix login" } },
        synced_at: "2026-07-20T10:01:00",
        start_date: null,
        target_date: null,
        created_date: "2026-07-19T10:00:00",
        activated_date: null,
        closed_date: null,
      },
      history: [
        {
          work_item_id: 42,
          area_path_id: 7,
          rev: 1,
          revised_by: null,
          revised_date: "2026-07-19T10:00:00",
          raw_json: { fields: { "System.State": "New" } },
          synced_at: "2026-07-20T10:01:00",
        },
      ],
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: details }), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchWorkItemDetails(42)).resolves.toEqual(details);
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:5001/api/work-items/42");
  });
});

describe("fetchCapacity", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("requests the selected capacity period and unwraps the snapshot", async () => {
    const snapshot = {
      generated_at: "2026-07-27T00:00:00",
      history_start: "2025-08-01T00:00:00",
      monthly_throughput: [],
      by_type: {},
      forecast: { conservative: 9, expected: 15, optimistic: 21 },
      flow_metrics: {},
      warnings: [],
      delivery_months: 3,
      is_reliable: true,
      selected_period: { year: 2026, quarter: 3 },
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: snapshot }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchCapacity(7, 2026, 3)).resolves.toEqual(snapshot);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:5001/api/capacity?area_path_id=7&year=2026&quarter=3",
    );
  });

  test("returns null when the selected area path has no capacity snapshot", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: null }), { status: 200 }),
    ));

    await expect(fetchCapacity(7, 2026, 3)).resolves.toBeNull();
  });
});
