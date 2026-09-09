// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";
import App from "./App";
import * as syncServiceClient from "./services/syncServiceClient";

vi.mock("./services/syncServiceClient", () => ({
  fetchUpdateStatus: vi.fn().mockResolvedValue({
    update_available: false,
    current_version: "0.1.0",
    latest_version: "0.1.0",
  }),
  startUpdate: vi.fn(),
}));

vi.mock("./pages/WorkItemsListPage", () => ({
  default: () => <div>Work items page</div>,
}));

vi.mock("./pages/FeaturesRoadmapPage", () => ({
  default: () => <div>Features roadmap page</div>,
}));

vi.mock("./pages/SynchronizationPage", () => ({
  default: () => <div>Synchronization page</div>,
}));

vi.mock("@astryxdesign/core/SideNav", () => ({
  SideNav: ({ children }: { children: React.ReactNode }) => <nav>{children}</nav>,
  SideNavItem: ({
    icon,
    label,
  }: {
    icon?: string;
    label: string;
  }) => <button data-icon={icon} type="button">{label}</button>,
}));

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
  HTMLDialogElement.prototype.showModal = function showModal() {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close() {
    this.removeAttribute("open");
  };
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("App navigation", () => {
  test("uses the Astryx wrench icon for synchronization", () => {
    render(<App />);

    expect(screen.getByRole("button", { name: "Synchronization" })).toHaveAttribute(
      "data-icon",
      "wrench",
    );
  });

  test("hides capacity from the main sidebar", () => {
    render(<App />);

    expect(screen.queryByRole("button", { name: "Capacity & Flow" })).not.toBeInTheDocument();
  });

  test("asks for confirmation before starting an update", async () => {
    vi.mocked(syncServiceClient.fetchUpdateStatus).mockResolvedValue({
      update_available: true,
      current_version: "0.1.0",
      latest_version: "0.2.0",
    });

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "Update now" }));
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent("unavailable for a few moments");
    expect(syncServiceClient.startUpdate).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "Update now" }));

    await waitFor(() => {
      expect(syncServiceClient.startUpdate).toHaveBeenCalledTimes(1);
    });
  });
});
