// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";
import App from "./App";

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
});

afterEach(() => {
  cleanup();
});

describe("App navigation", () => {
  test("uses the Astryx wrench icon for synchronization", () => {
    render(<App />);

    expect(screen.getByRole("button", { name: "Synchronization" })).toHaveAttribute(
      "data-icon",
      "wrench",
    );
  });

  test("uses the Astryx flow icon for capacity", () => {
    render(<App />);

    expect(screen.getByRole("button", { name: "Capacity & Flow" })).toHaveAttribute(
      "data-icon",
      "arrowsUpDown",
    );
  });
});
