import type {
  WorkItem,
  WorkItemDetails,
  PaginatedResponse,
} from "../models/workItem";
import type { AreaPath } from "../models/areaPath";
import type { FeatureTreeItem } from "../models/feature";
import type { CapacitySnapshot } from "../models/capacity";

const BASE_URL = import.meta.env.VITE_API_READ_BASE_URL ?? "http://127.0.0.1:5001";

export interface WorkItemListParams {
  areaPathId?: number;
  search?: string;
  page?: number;
  pageSize?: number;
  orderBy?: "changed_date" | "id" | "title";
  orderDir?: "asc" | "desc";
}

export async function fetchWorkItems(
  params: WorkItemListParams = {}
): Promise<PaginatedResponse<WorkItem>> {
  const query = new URLSearchParams();
  if (params.areaPathId !== undefined) query.set("area_path_id", String(params.areaPathId));
  if (params.search) query.set("search", params.search);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.pageSize ?? 50));
  query.set("order_by", params.orderBy ?? "changed_date");
  query.set("order_dir", params.orderDir ?? "desc");

  const response = await fetch(`${BASE_URL}/api/work-items?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch work items: ${response.status}`);
  }
  return response.json();
}

export async function fetchWorkItemDetails(id: number): Promise<WorkItemDetails> {
  const response = await fetch(`${BASE_URL}/api/work-items/${encodeURIComponent(String(id))}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch work item details: ${response.status}`);
  }
  const body = await response.json();
  return body.data;
}

export async function fetchAreaPaths(): Promise<AreaPath[]> {
  const response = await fetch(`${BASE_URL}/api/area-paths`);
  if (!response.ok) {
    throw new Error(`Failed to fetch area paths: ${response.status}`);
  }
  return response.json();
}

export async function fetchFeaturesTree(areaPathId: number): Promise<FeatureTreeItem[]> {
  const response = await fetch(
    `${BASE_URL}/api/features-tree?area_path_id=${encodeURIComponent(String(areaPathId))}`
  );
  if (!response.ok) {
    throw new Error(`Failed to fetch features tree: ${response.status}`);
  }
  const body = await response.json();
  return body.data;
}

export async function fetchCapacity(
  areaPathId: number,
  year: number,
  quarter: number,
): Promise<CapacitySnapshot | null> {
  const query = new URLSearchParams({
    area_path_id: String(areaPathId),
    year: String(year),
    quarter: String(quarter),
  });
  const response = await fetch(`${BASE_URL}/api/capacity?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch capacity: ${response.status}`);
  }
  const body = await response.json();
  return body.data;
}
