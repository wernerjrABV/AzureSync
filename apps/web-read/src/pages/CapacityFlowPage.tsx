import { useEffect, useMemo, useState } from "react";
import { Badge } from "@astryxdesign/core/Badge";
import { Banner } from "@astryxdesign/core/Banner";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Card, HStack, VStack } from "@astryxdesign/core/Layout";
import { Selector } from "@astryxdesign/core/Selector";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Table, proportional } from "@astryxdesign/core/Table";
import { Text } from "@astryxdesign/core/Text";
import type { AreaPath } from "../models/areaPath";
import type { CapacitySnapshot } from "../models/capacity";
import { fetchAreaPaths, fetchCapacity } from "../services/apiReadClient";

type TableRow = Record<string, unknown>;

function currentQuarter(date: Date): number {
  return Math.floor(date.getMonth() / 3) + 1;
}

function formatDuration(seconds: number): string {
  if (seconds === 0) return "0h";
  const totalHours = Math.round(seconds / 3_600);
  const days = Math.floor(totalHours / 24);
  const hours = totalHours % 24;
  return days > 0 ? `${days}d ${hours}h` : `${hours}h`;
}

function forecastCard(title: string, value: number) {
  return (
    <Card>
      <VStack gap={1}>
        <Text as="div" weight="semibold">{title}</Text>
        <Text as="div" size="xl" weight="bold">{String(value)}</Text>
        <Text as="div">Items in selected quarter</Text>
      </VStack>
    </Card>
  );
}

function throughputRow(snapshot: CapacitySnapshot): TableRow {
  return snapshot.monthly_throughput.reduce<TableRow>(
    (row, bucket) => ({ ...row, [bucket.month]: bucket.count }),
    { series: "Completed items" },
  );
}

export default function CapacityFlowPage() {
  const now = useMemo(() => new Date(), []);
  const [areaPaths, setAreaPaths] = useState<AreaPath[]>([]);
  const [areaPathsLoaded, setAreaPathsLoaded] = useState(false);
  const [areaPathId, setAreaPathId] = useState<number | undefined>();
  const [selectedYear, setSelectedYear] = useState(String(now.getFullYear()));
  const [selectedQuarter, setSelectedQuarter] = useState(String(currentQuarter(now)));
  const [snapshot, setSnapshot] = useState<CapacitySnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const years = useMemo(() => (
    Array.from({ length: 5 }, (_, index) => now.getFullYear() - 2 + index)
      .reverse()
      .map((year) => ({ value: String(year), label: String(year) }))
  ), [now]);

  useEffect(() => {
    let active = true;
    fetchAreaPaths()
      .then((paths) => {
        if (!active) return;
        setAreaPaths(paths);
        if (paths.length > 0) setAreaPathId(paths[0].id);
      })
      .catch(() => {
        if (active) setAreaPaths([]);
      })
      .finally(() => {
        if (active) setAreaPathsLoaded(true);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (areaPathId === undefined) return;
    let active = true;
    setLoading(true);
    setError(null);
    setSnapshot(null);
    fetchCapacity(areaPathId, Number(selectedYear), Number(selectedQuarter))
      .then((data) => {
        if (active) setSnapshot(data);
      })
      .catch((err: Error) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [areaPathId, selectedQuarter, selectedYear]);

  const typeRows = snapshot ? Object.entries(snapshot.by_type).map(([workItemType, value]) => ({
    workItemType,
    conservative: value.forecast.conservative,
    expected: value.forecast.expected,
    optimistic: value.forecast.optimistic,
    medianCycle: formatDuration(snapshot.flow_metrics[workItemType]?.development_cycle_seconds ?? 0),
  })) : [];
  const flowRows = snapshot ? Object.entries(snapshot.flow_metrics).map(([workItemType, value]) => ({
    workItemType,
    upstream: formatDuration(value.upstream_seconds),
    downstream: formatDuration(value.downstream_seconds),
    cycle: formatDuration(value.development_cycle_seconds),
  })) : [];
  const statusRows = snapshot ? Object.entries(snapshot.flow_metrics).flatMap(([workItemType, value]) => (
    Object.entries(value.by_status).map(([status, seconds]) => ({
      workItemType,
      status,
      duration: formatDuration(seconds),
    }))
  )) : [];

  return (
    <Card>
      <VStack gap={4}>
        <HStack gap={4} align="end" wrap="wrap">
          <Selector
            label="Area path"
            hasSearch
            value={areaPathId !== undefined ? String(areaPathId) : undefined}
            onChange={(value) => setAreaPathId(value ? Number(value) : undefined)}
            options={areaPaths.map((areaPath) => ({
              value: String(areaPath.id),
              label: areaPath.area_path,
            }))}
            width={280}
          />
          <Selector
            label="Year"
            value={selectedYear}
            onChange={setSelectedYear}
            options={years}
            width={140}
          />
          <Selector
            label="Quarter"
            value={selectedQuarter}
            onChange={setSelectedQuarter}
            options={[1, 2, 3, 4].map((quarter) => ({
              value: String(quarter),
              label: `Q${quarter}`,
            }))}
            width={140}
          />
        </HStack>

        {!areaPathsLoaded && <Spinner label="Loading area paths" />}

        {areaPathsLoaded && areaPaths.length === 0 && (
          <EmptyState
            title="No area paths configured"
            description="Configure at least one area path in the sync service to see capacity forecasts."
          />
        )}

        {areaPathId !== undefined && loading && !error && (
          <Spinner label="Loading capacity forecast" />
        )}

        {error && (
          <Banner
            status="error"
            title="Error loading capacity forecast"
            description={error}
          />
        )}

        {areaPathId !== undefined && !loading && !error && snapshot === null && (
          <EmptyState
            title="Capacity forecast unavailable"
            description="A complete history backfill with at least three delivery months is required."
          />
        )}

        {snapshot && !loading && !error && (
          <>
            {!snapshot.is_reliable && (
              <EmptyState
                title="Capacity forecast unavailable"
                description="At least three months containing completed eligible work are required."
              />
            )}

            {snapshot.is_reliable && (
              <HStack gap={4} wrap="wrap">
                {forecastCard("Conservative forecast", snapshot.forecast.conservative)}
                {forecastCard("Expected forecast", snapshot.forecast.expected)}
                {forecastCard("Optimistic forecast", snapshot.forecast.optimistic)}
              </HStack>
            )}

            {snapshot.warnings.map((warning, index) => (
              <Banner
                key={`${warning.code}-${warning.work_item_type ?? index}`}
                status="warning"
                title={warning.work_item_type ? `${warning.work_item_type} warning` : "Capacity warning"}
                description={warning.message}
              />
            ))}

            <VStack gap={2}>
              <Text as="div" weight="semibold">Forecast by work item type</Text>
              {typeRows.length > 0 ? (
                <Table
                  data={typeRows as TableRow[]}
                  idKey="workItemType"
                  density="balanced"
                  dividers="rows"
                  columns={[
                    { key: "workItemType", header: "Work item type", width: proportional(2) },
                    { key: "conservative", header: "Conservative", width: proportional(1) },
                    { key: "expected", header: "Expected", width: proportional(1) },
                    { key: "optimistic", header: "Optimistic", width: proportional(1) },
                    { key: "medianCycle", header: "Median cycle", width: proportional(1) },
                  ]}
                />
              ) : <Text>No eligible work item types in the snapshot.</Text>}
            </VStack>

            <VStack gap={2}>
              <Text as="div" weight="semibold">12-month throughput</Text>
              <Table
                data={[throughputRow(snapshot)]}
                idKey="series"
                density="compact"
                dividers="rows"
                columns={[
                  { key: "series", header: "Series", width: proportional(2) },
                  ...snapshot.monthly_throughput.map((bucket) => ({
                    key: bucket.month,
                    header: bucket.month,
                    width: proportional(1),
                  })),
                ]}
              />
            </VStack>

            <VStack gap={2}>
              <Text as="div" weight="semibold">Flow metrics</Text>
              {flowRows.length > 0 ? (
                <Table
                  data={flowRows as TableRow[]}
                  idKey="workItemType"
                  density="balanced"
                  dividers="rows"
                  columns={[
                    { key: "workItemType", header: "Work item type", width: proportional(2) },
                    { key: "upstream", header: "Upstream", width: proportional(1) },
                    { key: "downstream", header: "Downstream", width: proportional(1) },
                    { key: "cycle", header: "Development cycle", width: proportional(1) },
                  ]}
                />
              ) : <Text>No flow metrics are available.</Text>}
            </VStack>

            <VStack gap={2}>
              <Text as="div" weight="semibold">Median status durations</Text>
              {statusRows.length > 0 ? (
                <Table
                  data={statusRows as TableRow[]}
                  idKey="status"
                  density="balanced"
                  dividers="rows"
                  columns={[
                    { key: "workItemType", header: "Work item type", width: proportional(2) },
                    { key: "status", header: "Status", width: proportional(2), renderCell: (row: TableRow) => <Badge label={String(row.status)} /> },
                    { key: "duration", header: "Median duration", width: proportional(1) },
                  ]}
                />
              ) : <Text>No status durations are available.</Text>}
            </VStack>
          </>
        )}
      </VStack>
    </Card>
  );
}
