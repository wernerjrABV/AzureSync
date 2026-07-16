import type { WorkItem, PaginatedResponse } from "../models/workItem";
import type { AreaPath } from "../models/areaPath";

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

export async function fetchAreaPaths(): Promise<AreaPath[]> {
  const response = await fetch(`${BASE_URL}/api/area-paths`);
  if (!response.ok) {
    throw new Error(`Failed to fetch area paths: ${response.status}`);
  }
  return response.json();
}
