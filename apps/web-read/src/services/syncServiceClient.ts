export interface SyncAreaPath {
  id: number;
  organization: string;
  project: string;
  area_path: string;
  incluir_subpaths: boolean;
  ativo: boolean;
  intervalo_minutos: number;
  is_running: boolean;
  last_sync_at: string | null;
  last_sync_status: string | null;
  last_sync_count: number | null;
  last_error_msg: string | null;
  created_at: string;
  history_loaded_at: string | null;
  sync_progress?: {
    phase: string;
    current: number;
    total: number | null;
  };
}

export interface AreaPathInput {
  organization: string;
  project: string;
  area_path: string;
  incluir_subpaths: boolean;
  ativo: boolean;
  intervalo_minutos: number;
}

export interface AzureDevOpsCredentialStatus {
  configured: boolean;
  updated_at: string | null;
}

export interface UpdateStatus {
  update_available: boolean;
  current_version: string;
  latest_version: string | null;
}

const BASE_URL =
  import.meta.env.VITE_API_READ_BASE_URL ?? "http://127.0.0.1:5001";

interface DataResponse<T> {
  data: T;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = options
    ? await fetch(`${BASE_URL}${path}`, options)
    : await fetch(`${BASE_URL}${path}`);

  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json();
      if (body && typeof body.error === "string") {
        detail = `: ${body.error}`;
      }
    } catch {
      // The status code is still useful when the error response is not JSON.
    }
    throw new Error(`Sync service request failed: ${response.status}${detail}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

function jsonOptions(method: "POST" | "PUT", body: AreaPathInput): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export async function fetchSyncAreaPaths(): Promise<SyncAreaPath[]> {
  return request<SyncAreaPath[]>("/api/area-paths");
}

export async function createSyncAreaPath(input: AreaPathInput): Promise<SyncAreaPath> {
  const response = await request<DataResponse<SyncAreaPath>>(
    "/api/area-paths",
    jsonOptions("POST", input)
  );
  return response.data;
}

export async function updateSyncAreaPath(
  id: number,
  input: AreaPathInput
): Promise<SyncAreaPath> {
  const response = await request<DataResponse<SyncAreaPath>>(
    `/api/area-paths/${encodeURIComponent(String(id))}`,
    jsonOptions("PUT", input)
  );
  return response.data;
}

export async function deleteSyncAreaPath(id: number): Promise<"deletion_requested" | undefined> {
  const response = await request<{ status: "deletion_requested" } | undefined>(
    `/api/area-paths/${encodeURIComponent(String(id))}`,
    {
    method: "DELETE",
    },
  );
  return response?.status;
}

export async function startAreaPathSync(id: number): Promise<void> {
  await request<{ status: "started" }>(
    `/api/area-paths/${encodeURIComponent(String(id))}/sync`,
    { method: "POST" }
  );
}

export async function forceAreaPathSync(id: number): Promise<void> {
  await request<{ status: "started"; stale_lock_released: boolean }>(
    `/api/area-paths/${encodeURIComponent(String(id))}/force-sync`,
    { method: "POST" }
  );
}

export async function cancelAreaPathSync(id: number): Promise<void> {
  await request<{ status: "cancellation_requested" }>(
    `/api/area-paths/${encodeURIComponent(String(id))}/cancel`,
    { method: "POST" }
  );
}

export async function cancelAllSyncs(): Promise<void> {
  await request<{ status: "cancellation_requested"; count: number }>(
    "/api/sync/cancel",
    { method: "POST" }
  );
}

export function fetchAzureDevOpsCredentialStatus(): Promise<AzureDevOpsCredentialStatus> {
  return request<AzureDevOpsCredentialStatus>("/api/settings/azure-devops");
}

export function saveAzureDevOpsCredential(
  apiKey: string
): Promise<AzureDevOpsCredentialStatus> {
  return request<AzureDevOpsCredentialStatus>("/api/settings/azure-devops", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export async function deleteAzureDevOpsCredential(): Promise<void> {
  await request<void>("/api/settings/azure-devops", { method: "DELETE" });
}

export function fetchUpdateStatus(): Promise<UpdateStatus> {
  return request<UpdateStatus>("/api/update");
}

export function startUpdate(): Promise<UpdateStatus & { status: "started" }> {
  return request<UpdateStatus & { status: "started" }>("/api/update", { method: "POST" });
}
