export interface WorkItem {
  id: number;
  area_path_id: number;
  title: string | null;
  work_item_type: string | null;
  state: string | null;
  assigned_to: string | null;
  changed_date: string | null;
  parent_id: number | null;
  raw_json: unknown;
  synced_at: string | null;
  start_date: string | null;
  target_date: string | null;
  created_date: string | null;
  activated_date: string | null;
  closed_date: string | null;
}

export interface WorkItemHistoryRevision {
  work_item_id: number;
  area_path_id: number;
  rev: number;
  revised_by: string | null;
  revised_date: string | null;
  raw_json: unknown;
  synced_at: string | null;
}

export interface WorkItemDetails {
  item: WorkItem;
  history: WorkItemHistoryRevision[];
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
  };
}
