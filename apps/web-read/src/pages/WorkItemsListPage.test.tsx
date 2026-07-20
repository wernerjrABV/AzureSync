// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Theme } from "@astryxdesign/core/theme";
import { neutralTheme } from "@astryxdesign/theme-neutral";
import { afterAll, afterEach, beforeAll, describe, expect, test, vi } from "vitest";
import WorkItemsListPage from "./WorkItemsListPage";
import * as apiReadClient from "../services/apiReadClient";
import type { WorkItem, WorkItemDetails } from "../models/workItem";

vi.mock("../services/apiReadClient", () => ({
  fetchAreaPaths: vi.fn(),
  fetchWorkItems: vi.fn(),
  fetchWorkItemDetails: vi.fn(),
}));

const workItem: WorkItem = {
  id: 42,
  area_path_id: 7,
  title: "Fix login",
  work_item_type: "Bug",
  state: "Active",
  assigned_to: "Ada Lovelace",
  changed_date: "2026-07-20T10:00:00",
  parent_id: 8,
  raw_json: { fields: { "System.Title": "Fix login" } },
  synced_at: "2026-07-20T10:01:00",
  start_date: "2026-07-19T10:00:00",
  target_date: "2026-07-30T10:00:00",
  created_date: "2026-07-18T10:00:00",
  activated_date: "2026-07-19T10:00:00",
  closed_date: null,
};

const details: WorkItemDetails = {
  item: workItem,
  history: [
    {
      work_item_id: 42,
      area_path_id: 7,
      rev: 1,
      revised_by: "Grace Hopper",
      revised_date: "2026-07-18T10:00:00",
      raw_json: { fields: { "System.State": "New" } },
      synced_at: "2026-07-20T10:01:00",
    },
    {
      work_item_id: 42,
      area_path_id: 7,
      rev: 2,
      revised_by: "Ada Lovelace",
      revised_date: "2026-07-20T10:00:00",
      raw_json: { fields: { "System.State": "Active" } },
      synced_at: "2026-07-20T10:01:00",
    },
  ],
};

const secondWorkItem: WorkItem = {
  ...workItem,
  id: 99,
  title: "Second issue",
  raw_json: { fields: { "System.Title": "Second issue" } },
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function renderPage() {
  return render(
    <Theme theme={neutralTheme}>
      <WorkItemsListPage />
    </Theme>,
  );
}

function expectFormattedJson(label: string, value: unknown) {
  const json = JSON.stringify(value, null, 2);
  const block = screen.getByLabelText(label);
  const code = block.querySelector("code");

  expect(block.tagName).toBe("PRE");
  expect(code).not.toBeNull();
  expect(code).toHaveTextContent(/"System\.(Title|State)"/);
  expect(code!.children).toHaveLength(json.split("\n").length);
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
  HTMLDialogElement.prototype.showModal = function showModal() {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close() {
    this.removeAttribute("open");
  };
  HTMLCanvasElement.prototype.getContext = vi.fn();
  window.scrollTo = vi.fn();
});

afterAll(() => {
  delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).showModal;
  delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).close;
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function mockListLoad(items: WorkItem[] = [workItem]) {
  vi.mocked(apiReadClient.fetchAreaPaths).mockResolvedValue([
    { id: 7, organization: "org", project: "project", area_path: "Engineering" },
  ]);
  vi.mocked(apiReadClient.fetchWorkItems).mockResolvedValue({
    data: items,
    pagination: { page: 1, page_size: 50, total: items.length },
  });
}

describe("WorkItemsListPage", () => {
  test("opens a detail drawer with a spinner, current data, raw JSON, and history after a row click", async () => {
    mockListLoad();
    const pendingDetails = deferred<WorkItemDetails>();
    vi.mocked(apiReadClient.fetchWorkItemDetails).mockReturnValue(pendingDetails.promise);

    renderPage();

    fireEvent.click(await screen.findByText("Fix login"));

    await waitFor(() => {
      expect(apiReadClient.fetchWorkItemDetails).toHaveBeenCalledWith(42);
    });
    expect(screen.getByText("Loading work item details")).toBeInTheDocument();

    pendingDetails.resolve(details);

    expect(await screen.findByText("Work item details")).toBeInTheDocument();
    expect(screen.getByText("ID: 42")).toBeInTheDocument();
    expect(screen.getByText("Title: Fix login")).toBeInTheDocument();
    expect(screen.getByText("Work item type: Bug")).toBeInTheDocument();
    expect(screen.getByText("State: Active")).toBeInTheDocument();
    expect(screen.getByText("Assigned to: Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Changed date: 2026-07-20T10:00:00")).toBeInTheDocument();
    expect(screen.getByText("Parent ID: 8")).toBeInTheDocument();
    expect(screen.getByText("Start date: 2026-07-19T10:00:00")).toBeInTheDocument();
    expect(screen.getByText("Target date: 2026-07-30T10:00:00")).toBeInTheDocument();
    expect(screen.getByText("Created date: 2026-07-18T10:00:00")).toBeInTheDocument();
    expect(screen.getByText("Activated date: 2026-07-19T10:00:00")).toBeInTheDocument();
    expect(screen.getByText("Closed date: —")).toBeInTheDocument();

    expectFormattedJson("Current raw JSON", details.item.raw_json);

    expect(screen.getAllByText(/^Revision \d+$/).map((heading) => heading.textContent)).toEqual([
      "Revision 1",
      "Revision 2",
    ]);
    expect(screen.getAllByText("Work item ID: 42")).toHaveLength(2);
    expect(screen.getAllByText("Area path ID: 7")).toHaveLength(3);
    expect(screen.getByText("Revised by: Grace Hopper")).toBeInTheDocument();
    expect(screen.getByText("Revised date: 2026-07-18T10:00:00")).toBeInTheDocument();
    expect(screen.getByText("Revised by: Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Revised date: 2026-07-20T10:00:00")).toBeInTheDocument();
    expect(screen.getAllByText("Synced at: 2026-07-20T10:01:00")).toHaveLength(3);
    expectFormattedJson("Revision 1 raw JSON", details.history[0].raw_json);
    expectFormattedJson("Revision 2 raw JSON", details.history[1].raw_json);
  });

  test("uses an em dash for every nullable current field when its value is null", async () => {
    mockListLoad();
    vi.mocked(apiReadClient.fetchWorkItemDetails).mockResolvedValue({
      item: {
        ...workItem,
        title: null,
        work_item_type: null,
        state: null,
        assigned_to: null,
        changed_date: null,
        parent_id: null,
        synced_at: null,
        start_date: null,
        target_date: null,
        created_date: null,
        activated_date: null,
        closed_date: null,
      },
      history: [],
    });

    renderPage();
    fireEvent.click(await screen.findByText("Fix login"));

    await screen.findByText("Current fields");

    [
      "Title",
      "Work item type",
      "State",
      "Assigned to",
      "Changed date",
      "Parent ID",
      "Synced at",
      "Start date",
      "Target date",
      "Created date",
      "Activated date",
      "Closed date",
    ].forEach((label) => {
      expect(screen.getByText(`${label}: —`)).toBeInTheDocument();
    });
  });

  test.each(["Enter", " "])("opens details when a row receives the %s key", async (key) => {
    mockListLoad();
    vi.mocked(apiReadClient.fetchWorkItemDetails).mockResolvedValue(details);

    renderPage();

    const row = (await screen.findByText("Fix login")).closest("tr");
    expect(row).toHaveAttribute("tabindex", "0");
    expect(row).toHaveAttribute("aria-label", "Open work item 42 details");

    fireEvent.keyDown(row!, { key });

    await waitFor(() => {
      expect(apiReadClient.fetchWorkItemDetails).toHaveBeenCalledWith(42);
    });
  });

  test("closes the detail drawer from its header control", async () => {
    mockListLoad();
    vi.mocked(apiReadClient.fetchWorkItemDetails).mockResolvedValue(details);

    renderPage();
    fireEvent.click(await screen.findByText("Fix login"));
    await screen.findByText("Current fields");

    const dialog = screen.getByText("Work item details").closest("dialog");
    expect(dialog).toHaveAttribute("open");

    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    await waitFor(() => {
      expect(dialog).not.toHaveAttribute("open");
      expect(screen.queryByText("Current fields")).not.toBeInTheDocument();
    });
  });

  test("shows an error banner when loading selected work item details fails", async () => {
    mockListLoad();
    vi.mocked(apiReadClient.fetchWorkItemDetails).mockRejectedValue(
      new Error("Azure DevOps is unavailable"),
    );

    renderPage();

    fireEvent.click(await screen.findByText("Fix login"));

    expect(await screen.findByText("Error loading work item details")).toBeInTheDocument();
    expect(screen.getByText("Azure DevOps is unavailable")).toBeInTheDocument();
  });

  test("ignores an older detail response after another row is selected", async () => {
    mockListLoad([workItem, secondWorkItem]);
    const firstResponse = deferred<WorkItemDetails>();
    const secondResponse = deferred<WorkItemDetails>();
    vi.mocked(apiReadClient.fetchWorkItemDetails).mockImplementation((id) => (
      id === workItem.id ? firstResponse.promise : secondResponse.promise
    ));

    renderPage();

    fireEvent.click(await screen.findByText("Fix login"));
    fireEvent.click(await screen.findByText("Second issue"));
    await act(async () => {
      secondResponse.resolve({ ...details, item: secondWorkItem });
      await secondResponse.promise;
    });

    expect(screen.getByText("Title: Second issue")).toBeInTheDocument();

    await act(async () => {
      firstResponse.resolve(details);
      await firstResponse.promise;
    });

    expect(screen.queryByText("Title: Fix login")).not.toBeInTheDocument();
  });
});
