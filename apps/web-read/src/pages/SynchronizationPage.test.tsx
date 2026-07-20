// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { StrictMode } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Theme } from "@astryxdesign/core/theme";
import { neutralTheme } from "@astryxdesign/theme-neutral";
import { afterAll, afterEach, beforeAll, describe, expect, test, vi } from "vitest";
import SynchronizationPage from "./SynchronizationPage";
import * as syncServiceClient from "../services/syncServiceClient";
import type { SyncAreaPath } from "../services/syncServiceClient";

vi.mock("../services/syncServiceClient", () => ({
  fetchSyncAreaPaths: vi.fn(),
  createSyncAreaPath: vi.fn(),
  updateSyncAreaPath: vi.fn(),
  deleteSyncAreaPath: vi.fn(),
  startAreaPathSync: vi.fn(),
}));

const areaPath: SyncAreaPath = {
  id: 7,
  organization: "acme",
  project: "intake",
  area_path: "Intake\\Platform",
  incluir_subpaths: true,
  ativo: true,
  intervalo_minutos: 30,
  is_running: false,
  last_sync_at: "2026-07-20T10:00:00",
  last_sync_status: "ok",
  last_sync_count: 12,
  last_error_msg: null,
  created_at: "2026-07-19T09:00:00",
  history_loaded_at: null,
};

function renderPage({ strictMode = false }: { strictMode?: boolean } = {}) {
  const page = strictMode ? (
    <StrictMode>
      <SynchronizationPage />
    </StrictMode>
  ) : (
    <SynchronizationPage />
  );

  return render(
    <Theme theme={neutralTheme}>
      {page}
    </Theme>,
  );
}

function mockInitialLoad(paths: SyncAreaPath[] = [areaPath]) {
  vi.mocked(syncServiceClient.fetchSyncAreaPaths).mockResolvedValue(paths);
}

function deferred<T>() {
  let resolve: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });

  return { promise, resolve: resolve! };
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
  vi.useRealTimers();
  vi.clearAllMocks();
  vi.mocked(syncServiceClient.fetchSyncAreaPaths).mockReset();
  vi.mocked(syncServiceClient.createSyncAreaPath).mockReset();
  vi.mocked(syncServiceClient.updateSyncAreaPath).mockReset();
  vi.mocked(syncServiceClient.deleteSyncAreaPath).mockReset();
  vi.mocked(syncServiceClient.startAreaPathSync).mockReset();
});

describe("SynchronizationPage", () => {
  test("keeps loading while a stale StrictMode initial request resolves", async () => {
    const staleRequest = deferred<SyncAreaPath[]>();
    const currentRequest = deferred<SyncAreaPath[]>();
    vi.mocked(syncServiceClient.fetchSyncAreaPaths)
      .mockReturnValueOnce(staleRequest.promise)
      .mockReturnValueOnce(currentRequest.promise)
      .mockReturnValue(currentRequest.promise);

    renderPage({ strictMode: true });

    expect(screen.getByLabelText("Loading synchronization settings")).toBeInTheDocument();

    staleRequest.resolve([areaPath]);
    await act(async () => {});

    expect(screen.getByLabelText("Loading synchronization settings")).toBeInTheDocument();

    currentRequest.resolve([areaPath]);
    expect(await screen.findByText("Intake\\Platform")).toBeInTheDocument();
    expect(screen.queryByLabelText("Loading synchronization settings")).not.toBeInTheDocument();
  });

  test("loads after StrictMode remounts the page effects", async () => {
    mockInitialLoad();

    renderPage({ strictMode: true });

    expect(await screen.findByText("Intake\\Platform")).toBeInTheDocument();
  });

  test("lists configured area paths and disables sync while one is already running", async () => {
    mockInitialLoad([{ ...areaPath, is_running: true, last_sync_status: null }]);

    renderPage();

    expect(await screen.findByText("Intake\\Platform")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Synchronize" })).toBeDisabled();
  });

  test("renders compact icon actions in a three-column card grid", async () => {
    mockInitialLoad([areaPath, { ...areaPath, id: 8, area_path: "Intake\\Mobile" }]);

    renderPage();

    expect(await screen.findByText("Intake\\Platform")).toBeInTheDocument();
    expect(screen.getByTestId("synchronization-card-grid")).toHaveClass("astryx-grid");
    expect(screen.getByRole("button", { name: "Synchronize Intake\\Platform" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Intake\\Platform" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete Intake\\Platform" })).toBeInTheDocument();
  });

  test("opens one form dialog for create and submits JSON-equivalent values", async () => {
    mockInitialLoad();
    vi.mocked(syncServiceClient.createSyncAreaPath).mockResolvedValue({
      ...areaPath,
      id: 8,
      area_path: "Intake\\Mobile",
    });

    renderPage();
    await screen.findByText("Intake\\Platform");

    fireEvent.click(screen.getByRole("button", { name: "Add area path" }));
    expect(screen.getByRole("heading", { name: "Add area path" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /^Interval \(minutes\)/ })).toHaveValue("60");

    fireEvent.change(screen.getByRole("textbox", { name: /^Organization/ }), { target: { value: "contoso" } });
    fireEvent.change(screen.getByRole("textbox", { name: /^Project/ }), { target: { value: "mobile" } });
    fireEvent.change(screen.getByRole("textbox", { name: /^Area path/ }), { target: { value: "Intake\\Mobile" } });
    fireEvent.change(screen.getByRole("textbox", { name: /^Interval \(minutes\)/ }), { target: { value: "15" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(syncServiceClient.createSyncAreaPath).toHaveBeenCalledWith({
        organization: "contoso",
        project: "mobile",
        area_path: "Intake\\Mobile",
        incluir_subpaths: true,
        ativo: true,
        intervalo_minutos: 15,
      });
    });
  });

  test("shows area path configuration and sync metadata including zero and null values", async () => {
    mockInitialLoad([{
      ...areaPath,
      ativo: false,
      incluir_subpaths: false,
      last_sync_at: null,
      last_sync_count: 0,
    }]);

    renderPage();

    await screen.findByText("Intake\\Platform");
    expect(screen.getByText("Inactive")).toBeInTheDocument();
    expect(screen.getByText("Include subpaths: No")).toBeInTheDocument();
    expect(screen.getByText("Last synchronized: Never")).toBeInTheDocument();
    expect(screen.getByText("Last sync count: 0")).toBeInTheDocument();
  });

  test("reuses the form dialog to edit an area path", async () => {
    mockInitialLoad();
    vi.mocked(syncServiceClient.updateSyncAreaPath).mockResolvedValue({
      ...areaPath,
      project: "updated-project",
    });

    renderPage();
    await screen.findByText("Intake\\Platform");

    fireEvent.click(screen.getByRole("button", { name: "Edit Intake\\Platform" }));
    expect(screen.getByText("Edit area path")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /^Organization/ })).toHaveValue("acme");

    fireEvent.change(screen.getByRole("textbox", { name: /^Project/ }), { target: { value: "updated-project" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(syncServiceClient.updateSyncAreaPath).toHaveBeenCalledWith(7, {
        organization: "acme",
        project: "updated-project",
        area_path: "Intake\\Platform",
        incluir_subpaths: true,
        ativo: true,
        intervalo_minutos: 30,
      });
    });
  });

  test("confirms deletion before removing an area path", async () => {
    mockInitialLoad();
    vi.mocked(syncServiceClient.deleteSyncAreaPath).mockResolvedValue(undefined);

    renderPage();
    await screen.findByText("Intake\\Platform");

    fireEvent.click(screen.getByRole("button", { name: "Delete Intake\\Platform" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Delete area path?");
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(syncServiceClient.deleteSyncAreaPath).toHaveBeenCalledWith(7);
    });
  });

  test.each([
    ["ok", "Synchronization completed successfully"],
    ["auth_error", "Synchronization requires Azure DevOps authentication"],
    ["error", "Synchronization failed"],
  ])("starts a sync, polls it to final %s status, and displays its message", async (status, message) => {
    vi.useFakeTimers();
    vi.mocked(syncServiceClient.fetchSyncAreaPaths)
      .mockResolvedValueOnce([areaPath])
      .mockResolvedValueOnce([{ ...areaPath, is_running: true, last_sync_status: null }])
      .mockResolvedValueOnce([{ ...areaPath, is_running: false, last_sync_status: status, last_error_msg: status === "error" ? "Azure DevOps is unavailable" : null }]);
    vi.mocked(syncServiceClient.startAreaPathSync).mockResolvedValue(undefined);

    renderPage();
    await act(async () => {});
    expect(screen.getByText("Intake\\Platform")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Synchronize" }));
    await act(async () => {});
    expect(syncServiceClient.startAreaPathSync).toHaveBeenCalledWith(7);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });

    expect(screen.getByText(message)).toBeInTheDocument();
    if (status === "error") {
      expect(screen.getByText("Azure DevOps is unavailable")).toBeInTheDocument();
    }
  });

  test("keeps polling after the first post-202 refresh still reports the previous final status", async () => {
    vi.mocked(syncServiceClient.fetchSyncAreaPaths)
      .mockResolvedValueOnce([areaPath])
      .mockResolvedValueOnce([{ ...areaPath, is_running: false, last_sync_status: "ok" }])
      .mockResolvedValueOnce([{ ...areaPath, is_running: true, last_sync_status: null }])
      .mockResolvedValueOnce([{ ...areaPath, is_running: false, last_sync_status: "error", last_error_msg: "Azure DevOps is unavailable" }]);
    vi.mocked(syncServiceClient.startAreaPathSync).mockResolvedValue(undefined);

    renderPage();
    await screen.findByText("Intake\\Platform");
    vi.useFakeTimers();

    fireEvent.click(screen.getByRole("button", { name: "Synchronize" }));
    await act(async () => {});

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(screen.getByText("Running")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(screen.getByText("Synchronization failed")).toBeInTheDocument();
  });

  test("keeps valid polling IDs when an older refresh resolves after a newer poll", async () => {
    const secondAreaPath = { ...areaPath, id: 8, area_path: "Intake\\Mobile" };
    const staleRefresh = deferred<SyncAreaPath[]>();
    vi.mocked(syncServiceClient.fetchSyncAreaPaths)
      .mockResolvedValueOnce([areaPath, secondAreaPath])
      .mockImplementationOnce(() => staleRefresh.promise)
      .mockResolvedValue([{ ...areaPath, is_running: true, last_sync_status: null }, { ...secondAreaPath, is_running: true, last_sync_status: null }]);
    vi.mocked(syncServiceClient.startAreaPathSync).mockResolvedValue(undefined);

    renderPage();
    await screen.findByText("Intake\\Mobile");
    vi.useFakeTimers();

    fireEvent.click(screen.getAllByRole("button", { name: "Synchronize" })[0]);
    await act(async () => {});
    fireEvent.click(screen.getAllByRole("button", { name: "Synchronize" })[1]);
    await act(async () => {});

    staleRefresh.resolve([{ ...areaPath, is_running: false }, { ...secondAreaPath, is_running: false }]);
    await act(async () => {});

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(syncServiceClient.fetchSyncAreaPaths).toHaveBeenCalledTimes(5);
  });

  test("cancels polling for an area path after it is deleted", async () => {
    vi.mocked(syncServiceClient.fetchSyncAreaPaths)
      .mockResolvedValueOnce([areaPath])
      .mockResolvedValueOnce([{ ...areaPath, is_running: true, last_sync_status: null }])
      .mockResolvedValue([]);
    vi.mocked(syncServiceClient.startAreaPathSync).mockResolvedValue(undefined);
    vi.mocked(syncServiceClient.deleteSyncAreaPath).mockResolvedValue(undefined);

    renderPage();
    await screen.findByText("Intake\\Platform");
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "Synchronize" }));
    await act(async () => {});

    fireEvent.click(screen.getByRole("button", { name: "Delete Intake\\Platform" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await act(async () => {});

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(syncServiceClient.fetchSyncAreaPaths).toHaveBeenCalledTimes(3);
  });

  test("cancels polling timers when the page unmounts", async () => {
    vi.mocked(syncServiceClient.fetchSyncAreaPaths)
      .mockResolvedValueOnce([areaPath])
      .mockResolvedValue([{ ...areaPath, is_running: true, last_sync_status: null }]);
    vi.mocked(syncServiceClient.startAreaPathSync).mockResolvedValue(undefined);

    const { unmount } = renderPage();
    await screen.findByText("Intake\\Platform");
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "Synchronize" }));
    await act(async () => {});

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(syncServiceClient.fetchSyncAreaPaths).toHaveBeenCalledTimes(2);
  });
});
