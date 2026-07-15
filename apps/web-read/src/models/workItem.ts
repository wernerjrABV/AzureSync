export interface WorkItem {
  id: number;
  area_path_id: number;
  title: string | null;
  work_item_type: string | null;
  state: string | null;
  assigned_to: string | null;
  changed_date: string | null;
  parent_id: number | null;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
  };
}
