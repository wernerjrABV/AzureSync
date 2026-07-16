import { describe, expect, test } from "vitest";
import { quarterKey, quarterLabel } from "./quarter";

describe("quarterKey", () => {
  test.each([
    ["2026-01-15T00:00:00", "2026-Q1"],
    ["2026-03-31T00:00:00", "2026-Q1"],
    ["2026-04-01T00:00:00", "2026-Q2"],
    ["2026-06-30T00:00:00", "2026-Q2"],
    ["2026-07-01T00:00:00", "2026-Q3"],
    ["2026-09-30T00:00:00", "2026-Q3"],
    ["2026-10-01T00:00:00", "2026-Q4"],
    ["2026-12-31T00:00:00", "2026-Q4"],
  ])("%s -> %s", (iso, expected) => {
    expect(quarterKey(iso)).toBe(expected);
  });
});

describe("quarterLabel", () => {
  test("formats as 'Qn YYYY'", () => {
    expect(quarterLabel("2026-Q3")).toBe("Q3 2026");
  });
});
