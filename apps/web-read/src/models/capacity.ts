export interface ForecastRange {
  conservative: number;
  expected: number;
  optimistic: number;
}

export interface MonthlyThroughput {
  month: string;
  count: number;
}

export interface CapacityByType {
  monthly_throughput: MonthlyThroughput[];
  forecast: ForecastRange;
  delivery_months: number;
  is_reliable: boolean;
}

export interface FlowMetric {
  by_status: Record<string, number>;
  upstream_seconds: number;
  downstream_seconds: number;
  development_cycle_seconds: number;
}

export interface CapacityWarning {
  code: string;
  message: string;
  work_item_type?: string;
}

export interface SelectedPeriod {
  year: number;
  quarter: number;
}

export interface CapacitySnapshot {
  generated_at: string;
  history_start: string | null;
  monthly_throughput: MonthlyThroughput[];
  by_type: Record<string, CapacityByType>;
  forecast: ForecastRange;
  flow_metrics: Record<string, FlowMetric>;
  warnings: CapacityWarning[];
  delivery_months: number;
  is_reliable: boolean;
  selected_period: SelectedPeriod;
}
