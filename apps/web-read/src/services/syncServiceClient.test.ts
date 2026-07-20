import { afterEach, describe, expect, test, vi } from "vitest";

import {
  createSyncAreaPath,
  deleteSyncAreaPath,
  fetchSyncAreaPaths,
  startAreaPathSync,
  updateSyncAreaPath,
} from "./syncServiceClient";

const areaPath = {
  id: 7,
  organization: "acme",
  project: "intake",
  area_path: "Intake\\Platform",
  incluir_subpaths: true,
  ativo: true,
  intervalo_minutos: 30,
  is_running: false,
  last_sync_at: "2026-07-20T10:00:00",
  last_sync_status: null,
  last_sync_count: 12,
  last_error_msg: null,
  created_at: "2026-07-19T09:00:00",
  history_loaded_at: null,
};

const input = {
  organization: areaPath.organization,
  project: areaPath.project,
  area_path: areaPath.area_path,
  incluir_subpaths: areaPath.incluir_subpaths,
  ativo: areaPath.ativo,
  intervalo_minutos: areaPath.intervalo_minutos,
};

describe("syncServiceClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("fetches and parses the sync area path list", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify([areaPath]), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchSyncAreaPaths()).resolves.toEqual([areaPath]);
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:5001/api/area-paths");
  });

  test("creates an area path with a JSON body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: areaPath }), { status: 201 })
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(createSyncAreaPath(input)).resolves.toEqual(areaPath);
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:5001/api/area-paths", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
  });

  test("updates an area path with a JSON body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ data: areaPath }), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(updateSyncAreaPath(7, input)).resolves.toEqual(areaPath);
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:5001/api/area-paths/7", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
  });

  test("deletes an area path without parsing a response body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(deleteSyncAreaPath(7)).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:5001/api/area-paths/7", {
      method: "DELETE",
    });
  });

  test("starts an area path sync without a request body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "started" }), { status: 202 })
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(startAreaPathSync(7)).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:5001/api/area-paths/7/sync", {
      method: "POST",
    });
  });

  test.each([
    ["list", () => fetchSyncAreaPaths()],
    ["create", () => createSyncAreaPath(input)],
    ["update", () => updateSyncAreaPath(7, input)],
    ["delete", () => deleteSyncAreaPath(7)],
    ["start sync", () => startAreaPathSync(7)],
  ])("rejects %s when the sync service returns a non-2xx response", async (_operation, call) => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 500 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(call()).rejects.toThrow("500");
  });
});
