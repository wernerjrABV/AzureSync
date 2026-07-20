import { useEffect, useMemo, useState } from "react";
import { Card } from "@astryxdesign/core/Layout";
import { HStack, VStack } from "@astryxdesign/core/Layout";
import { Divider } from "@astryxdesign/core/Divider";
import { Selector } from "@astryxdesign/core/Selector";
import { Banner } from "@astryxdesign/core/Banner";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Spinner } from "@astryxdesign/core/Spinner";
import GanttChart from "../components/GanttChart";
import { fetchAreaPaths, fetchFeaturesTree } from "../services/apiReadClient";
import { buildFeatureTree } from "../utils/buildFeatureTree";
import type { AreaPath } from "../models/areaPath";
import type { FeatureTreeItem } from "../models/feature";
import type { FeatureTreeNode } from "../utils/buildFeatureTree";

const QUARTER_OPTIONS = [
  { value: "all", label: "All quarters" },
  { value: "1", label: "Q1" },
  { value: "2", label: "Q2" },
  { value: "3", label: "Q3" },
  { value: "4", label: "Q4" },
];

function currentQuarter(date: Date): number {
  return Math.floor(date.getMonth() / 3) + 1;
}

function itemDates(item: FeatureTreeItem): string[] {
  return [item.start_date, item.target_date, item.activated_date, item.closed_date].filter(
    (date): date is string => date !== null,
  );
}

function filterTreeByPeriod(
  roots: FeatureTreeNode[],
  year: number,
  quarter: string,
): FeatureTreeNode[] {
  const startMonth = quarter === "all" ? 0 : (Number(quarter) - 1) * 3;
  const start = new Date(year, startMonth, 1);
  const end = quarter === "all"
    ? new Date(year + 1, 0, 1)
    : new Date(year, startMonth + 3, 1);

  const matches = (node: FeatureTreeNode): boolean => {
    const periods = [
      [node.startDate, node.targetDate],
      [node.executedStartDate, node.executedEndDate],
    ];
    return periods.some(([periodStart, periodEnd]) => {
      const first = periodStart ?? periodEnd;
      const last = periodEnd ?? periodStart;
      if (first === null || last === null) return false;
      return new Date(last) >= start && new Date(first) < end;
    });
  };

  const filter = (nodes: FeatureTreeNode[]): FeatureTreeNode[] =>
    nodes.flatMap((node) => {
      const children = filter(node.children);
      return matches(node) || children.length > 0 ? [{ ...node, children }] : [];
    });

  return filter(roots);
}

export default function FeaturesRoadmapPage() {
  const [areaPaths, setAreaPaths] = useState<AreaPath[]>([]);
  const [areaPathsLoaded, setAreaPathsLoaded] = useState(false);
  const [areaPathId, setAreaPathId] = useState<number | undefined>(undefined);
  const [items, setItems] = useState<FeatureTreeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const now = new Date();
  const [selectedYear, setSelectedYear] = useState(String(now.getFullYear()));
  const [selectedQuarter, setSelectedQuarter] = useState(String(currentQuarter(now)));

  useEffect(() => {
    fetchAreaPaths()
      .then((paths) => {
        setAreaPaths(paths);
        if (paths.length > 0) {
          setAreaPathId(paths[0].id);
        }
      })
      .catch(() => {
        /* handled below via areaPathsLoaded + empty areaPaths */
      })
      .finally(() => setAreaPathsLoaded(true));
  }, []);

  useEffect(() => {
    if (areaPathId === undefined) {
      return;
    }
    setLoading(true);
    setError(null);
    fetchFeaturesTree(areaPathId)
      .then(setItems)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [areaPathId]);

  const tree = buildFeatureTree(items);
  const years = useMemo(() => {
    const values = new Set(items.flatMap(itemDates).map((date) => new Date(date).getFullYear()));
    values.add(now.getFullYear());
    return [...values].sort((a, b) => b - a).map((year) => ({ value: String(year), label: String(year) }));
  }, [items]);
  const filteredTree = filterTreeByPeriod(tree, Number(selectedYear), selectedQuarter);

  return (
    <Card>
      <VStack gap={4}>
      <HStack gap={4} align="end" wrap="wrap">
        <Selector
          label="Area path"
          hasSearch
          value={areaPathId !== undefined ? String(areaPathId) : undefined}
          onChange={(value) => setAreaPathId(value ? Number(value) : undefined)}
          options={areaPaths.map((ap) => ({ value: String(ap.id), label: ap.area_path }))}
          width={280}
        />
        <Selector
          label="Year"
          value={selectedYear}
          onChange={(value) => {
            setSelectedYear(value);
            setSelectedQuarter("all");
          }}
          options={years}
          width={140}
        />
        <Selector
          label="Quarter"
          value={selectedQuarter}
          onChange={setSelectedQuarter}
          options={QUARTER_OPTIONS}
          width={160}
        />
      </HStack>

      <Divider variant="subtle" />

      {error && (
        <Banner status="error" title="Error loading features roadmap" description={error} />
      )}

      {areaPathsLoaded && areaPaths.length === 0 && (
        <EmptyState
          title="No area paths configured"
          description="Configure at least one area path in the sync service to see the features roadmap."
        />
      )}

      {!areaPathsLoaded && <Spinner label="Loading area paths" />}

      {areaPathId !== undefined && loading && !error && <Spinner label="Loading features roadmap" />}

      {areaPathId !== undefined && !loading && !error && tree.length === 0 && (
        <EmptyState
          title="No features found"
          description="No Feature, Epic, or Solution work items in this area path."
        />
      )}

      {areaPathId !== undefined && !loading && !error && tree.length > 0 && filteredTree.length === 0 && (
        <EmptyState
          title="No items in selected period"
          description="No roadmap items have planned or executed dates in the selected year and quarter."
        />
      )}

      {areaPathId !== undefined && !loading && !error && filteredTree.length > 0 && (
        <GanttChart roots={filteredTree} />
      )}
      </VStack>
    </Card>
  );
}
