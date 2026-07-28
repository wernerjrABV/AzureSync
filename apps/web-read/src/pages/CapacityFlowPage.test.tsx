// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

const secondAreaPath = {
  id: 8,
  organization: "acme",
  project: "delivery",
  area_path: "Delivery\\Mobile",
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

const unreliableSnapshot = {
  ...reliableSnapshot,
  is_reliable: false,
  forecast: { conservative: 0, expected: 0, optimistic: 0 },
};

const twelveMonthSnapshot = {
  ...reliableSnapshot,
  monthly_throughput: [
    { month: "2025-08", count: 2 },
    { month: "2025-09", count: 0 },
    { month: "2025-10", count: 3 },
    { month: "2025-11", count: 4 },
    { month: "2025-12", count: 5 },
    { month: "2026-01", count: 6 },
    { month: "2026-02", count: 7 },
    { month: "2026-03", count: 8 },
    { month: "2026-04", count: 9 },
    { month: "2026-05", count: 10 },
    { month: "2026-06", count: 11 },
    { month: "2026-07", count: 12 },
  ],
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
  vi.useRealTimers();
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

  test("shows an API error when the initial area path request is rejected", async () => {
    vi.mocked(apiReadClient.fetchAreaPaths).mockRejectedValue(new Error("Area paths endpoint unavailable"));

    renderPage();

    expect(await screen.findByText("Error loading area paths")).toBeInTheDocument();
    expect(screen.getByText("Area paths endpoint unavailable")).toBeInTheDocument();
    expect(screen.queryByText("No area paths configured")).not.toBeInTheDocument();
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

  test("requests the current period after the initial area path is loaded", async () => {
    const now = new Date();
    const year = now.getFullYear();
    const quarter = Math.floor(now.getMonth() / 3) + 1;
    vi.mocked(apiReadClient.fetchAreaPaths).mockResolvedValue([areaPath]);
    vi.mocked(apiReadClient.fetchCapacity).mockResolvedValue(reliableSnapshot);

    renderPage();

    await act(async () => {});

    expect(apiReadClient.fetchCapacity).toHaveBeenCalledWith(7, year, quarter);
  });

  test("refetches capacity when the selected quarter changes", async () => {
    const now = new Date();
    const year = now.getFullYear();
    const initialQuarter = Math.floor(now.getMonth() / 3) + 1;
    const selectedQuarter = initialQuarter === 4 ? 3 : 4;
    vi.mocked(apiReadClient.fetchAreaPaths).mockResolvedValue([areaPath]);
    vi.mocked(apiReadClient.fetchCapacity).mockResolvedValue(reliableSnapshot);

    renderPage();

    await act(async () => {});
    expect(apiReadClient.fetchCapacity).toHaveBeenCalledWith(7, year, initialQuarter);
    fireEvent.click(screen.getByRole("combobox", { name: "Quarter" }));
    fireEvent.click(await screen.findByRole("option", { name: `Q${selectedQuarter}` }));

    await act(async () => {});

    expect(apiReadClient.fetchCapacity).toHaveBeenLastCalledWith(7, year, selectedQuarter);
  });

  test("refetches capacity when the selected area path changes", async () => {
    const now = new Date();
    const year = now.getFullYear();
    const quarter = Math.floor(now.getMonth() / 3) + 1;
    vi.mocked(apiReadClient.fetchAreaPaths).mockResolvedValue([areaPath, secondAreaPath]);
    vi.mocked(apiReadClient.fetchCapacity).mockResolvedValue(reliableSnapshot);

    renderPage();

    await act(async () => {});
    expect(apiReadClient.fetchCapacity).toHaveBeenCalledWith(7, year, quarter);
    fireEvent.click(screen.getByRole("button", { name: "Area path" }));
    fireEvent.click(await screen.findByRole("option", { name: "Delivery\\Mobile" }));

    await act(async () => {});

    expect(apiReadClient.fetchCapacity).toHaveBeenLastCalledWith(8, year, quarter);
  });

  test("hides every forecast card when the snapshot is unreliable", async () => {
    vi.mocked(apiReadClient.fetchAreaPaths).mockResolvedValue([areaPath]);
    vi.mocked(apiReadClient.fetchCapacity).mockResolvedValue(unreliableSnapshot);

    renderPage();

    expect(await screen.findByText("Capacity forecast unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Conservative forecast")).not.toBeInTheDocument();
    expect(screen.queryByText("Expected forecast")).not.toBeInTheDocument();
    expect(screen.queryByText("Optimistic forecast")).not.toBeInTheDocument();
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

  test("renders every monthly throughput bucket in the 12-month table", async () => {
    vi.mocked(apiReadClient.fetchAreaPaths).mockResolvedValue([areaPath]);
    vi.mocked(apiReadClient.fetchCapacity).mockResolvedValue(twelveMonthSnapshot);

    renderPage();

    expect(await screen.findByText("12-month throughput")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "2025-08" })).toBeInTheDocument();
    const finalMonthHeader = screen.getByRole("columnheader", { name: "2026-07" });
    const throughputTable = finalMonthHeader.closest("table");
    expect(throughputTable).not.toBeNull();
    expect(within(throughputTable!).getByRole("cell", { name: "12" })).toBeInTheDocument();
  });
});
