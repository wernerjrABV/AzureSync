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
    expect(screen.getByText("Assigned to: Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText(/\"System.Title\": \"Fix login\"/)).toBeInTheDocument();
    expect(screen.getByText("Revision 1")).toBeInTheDocument();
    expect(screen.getByText("Revision 2")).toBeInTheDocument();
    expect(screen.getByText(/\"System.State\": \"Active\"/)).toBeInTheDocument();
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
