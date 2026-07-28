// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Theme } from "@astryxdesign/core/theme";
import { neutralTheme } from "@astryxdesign/theme-neutral";
import { afterAll, afterEach, beforeAll, describe, expect, test, vi } from "vitest";
import CapacityFlowPage from "./CapacityFlowPage";
import * as apiReadClient from "../services/apiReadClient";

vi.mock("../services/apiReadClient", () => ({
  fetchAreaPaths: vi.fn(),
  fetchCapacity: vi.fn(),
}));

const areaPath = {
  id: 7,
  organization: "acme",
  project: "intake",
  area_path: "Intake\\Platform",
};

const reliableSnapshot = {
  generated_at: "2026-07-27T00:00:00",
  history_start: "2025-08-01T00:00:00",
  monthly_throughput: [
    { month: "2025-08", count: 2 },
    { month: "2025-09", count: 0 },
    { month: "2025-10", count: 3 },
  ],
  by_type: {
    "User Story": {
      monthly_throughput: [],
      forecast: { conservative: 6, expected: 9, optimistic: 12 },
      delivery_months: 3,
      is_reliable: true,
    },
  },
  forecast: { conservative: 9, expected: 15, optimistic: 21 },
  flow_metrics: {
    "User Story": {
      by_status: { Development: 86_400 },
      upstream_seconds: 0,
      downstream_seconds: 86_400,
      development_cycle_seconds: 86_400,
    },
  },
  warnings: [{ code: "history_gap", message: "One month has no completed work." }],
  delivery_months: 3,
  is_reliable: true,
  selected_period: { year: 2026, quarter: 3 },
};

function renderPage() {
  return render(
    <Theme theme={neutralTheme}>
      <CapacityFlowPage />
    </Theme>,
  );
}

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  HTMLCanvasElement.prototype.getContext = vi.fn();
});

afterAll(() => {
  vi.unstubAllGlobals();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.mocked(apiReadClient.fetchAreaPaths).mockReset();
  vi.mocked(apiReadClient.fetchCapacity).mockReset();
});

describe("CapacityFlowPage", () => {
  test("shows loading while area paths are requested", () => {
    vi.mocked(apiReadClient.fetchAreaPaths).mockReturnValue(new Promise(() => {}));

    renderPage();

    expect(screen.getByLabelText("Loading area paths")).toBeInTheDocument();
  });

  test("shows no area paths when none are configured", async () => {
    vi.mocked(apiReadClient.fetchAreaPaths).mockResolvedValue([]);

    renderPage();

    expect(await screen.findByText("No area paths configured")).toBeInTheDocument();
  });

  test("shows unavailable forecast for a missing snapshot", async () => {
    vi.mocked(apiReadClient.fetchAreaPaths).mockResolvedValue([areaPath]);
    vi.mocked(apiReadClient.fetchCapacity).mockResolvedValue(null);

    renderPage();

    expect(await screen.findByText("Capacity forecast unavailable")).toBeInTheDocument();
  });

  test("shows the API error for a selected area path", async () => {
    vi.mocked(apiReadClient.fetchAreaPaths).mockResolvedValue([areaPath]);
    vi.mocked(apiReadClient.fetchCapacity).mockRejectedValue(new Error("Capacity endpoint unavailable"));

    renderPage();

    expect(await screen.findByText("Error loading capacity forecast")).toBeInTheDocument();
    expect(screen.getByText("Capacity endpoint unavailable")).toBeInTheDocument();
  });

  test("renders reliable forecasts, flow tables, and warnings", async () => {
    vi.mocked(apiReadClient.fetchAreaPaths).mockResolvedValue([areaPath]);
    vi.mocked(apiReadClient.fetchCapacity).mockResolvedValue(reliableSnapshot);

    renderPage();

    expect(await screen.findByText("Conservative forecast")).toBeInTheDocument();
    expect(screen.getByText("Expected forecast")).toBeInTheDocument();
    expect(screen.getByText("Optimistic forecast")).toBeInTheDocument();
    expect(screen.getAllByText("User Story")).toHaveLength(3);
    expect(screen.getByText("One month has no completed work.")).toBeInTheDocument();
    expect(screen.getByText("Development")).toBeInTheDocument();
  });
});
