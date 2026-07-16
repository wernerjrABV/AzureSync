export interface FeatureTreeItem {
  id: number;
  title: string | null;
  work_item_type: string | null;
  parent_id: number | null;
  start_date: string | null;
  target_date: string | null;
}
