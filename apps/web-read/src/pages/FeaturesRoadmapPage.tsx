import { useEffect, useState } from "react";
import { Card } from "@astryxdesign/core/Layout";
import { HStack } from "@astryxdesign/core/Layout";
import { Selector } from "@astryxdesign/core/Selector";
import { Banner } from "@astryxdesign/core/Banner";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Badge } from "@astryxdesign/core/Badge";
import { TreeList, type TreeListItemData } from "@astryxdesign/core/TreeList";
import GanttChart from "../components/GanttChart";
import { fetchAreaPaths, fetchFeaturesTree } from "../services/apiReadClient";
import { buildFeatureTree, stateToBadgeVariant, type FeatureTreeNode } from "../utils/buildFeatureTree";
import { quarterKey, quarterLabel } from "../utils/quarter";
import type { AreaPath } from "../models/areaPath";
import type { FeatureTreeItem } from "../models/feature";

function formatDate(iso: string | null): string {
  return iso === null ? "—" : iso.slice(0, 10);
}

function nodeToTreeItem(node: FeatureTreeNode): TreeListItemData {
  return {
    id: String(node.id),
    label: `#${node.id} ${node.title}`,
    description: `${node.workItemType} · ${formatDate(node.startDate)} → ${formatDate(node.targetDate)}`,
    endContent: <Badge variant={stateToBadgeVariant(node.state)} label={node.state ?? "Unknown"} />,
    isExpanded: node.workItemType === "Epic",
    children:
      node.children.length > 0
        ? toTreeItemsWithQuarterSeparators(node.children, String(node.id))
        : undefined,
  };
}

// Nodes are already sorted most-recent-first (buildFeatureTree). This walks
// that order and inserts a non-interactive quarter-header row each time the
// effectiveDate's quarter changes from the previous sibling's.
function toTreeItemsWithQuarterSeparators(
  nodes: FeatureTreeNode[],
  parentId: string
): TreeListItemData[] {
  const result: TreeListItemData[] = [];
  let lastQuarter: string | null = null;
  for (const node of nodes) {
    const currentQuarter = node.effectiveDate ? quarterKey(node.effectiveDate) : "undated";
    if (currentQuarter !== lastQuarter) {
      result.push({
        id: `quarter-${parentId}-${currentQuarter}`,
        label: currentQuarter === "undated" ? "No date" : quarterLabel(currentQuarter),
        isDisabled: true,
      });
      lastQuarter = currentQuarter;
    }
    result.push(nodeToTreeItem(node));
  }
  return result;
}

export default function FeaturesRoadmapPage() {
  const [areaPaths, setAreaPaths] = useState<AreaPath[]>([]);
  const [areaPathsLoaded, setAreaPathsLoaded] = useState(false);
  const [areaPathId, setAreaPathId] = useState<number | undefined>(undefined);
  const [items, setItems] = useState<FeatureTreeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  return (
    <Card>
      <HStack gap={4} align="end" wrap="wrap">
        <Selector
          label="Area path"
          hasSearch
          value={areaPathId !== undefined ? String(areaPathId) : undefined}
          onChange={(value) => setAreaPathId(value ? Number(value) : undefined)}
          options={areaPaths.map((ap) => ({ value: String(ap.id), label: ap.area_path }))}
          width={280}
        />
      </HStack>

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

      {areaPathId !== undefined && !loading && !error && tree.length > 0 && (
        <>
          <GanttChart roots={tree} />
          <TreeList items={toTreeItemsWithQuarterSeparators(tree, "root")} density="balanced" />
        </>
      )}
    </Card>
  );
}
