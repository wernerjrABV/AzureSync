import { useEffect, useState } from "react";
import { Card } from "@astryxdesign/core/Layout";
import { HStack } from "@astryxdesign/core/Layout";
import { Selector } from "@astryxdesign/core/Selector";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Table, proportional, pixel } from "@astryxdesign/core/Table";
import { Pagination } from "@astryxdesign/core/Pagination";
import { Banner } from "@astryxdesign/core/Banner";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Badge } from "@astryxdesign/core/Badge";
import { fetchWorkItems, fetchAreaPaths } from "../services/apiReadClient";
import type { WorkItem } from "../models/workItem";
import type { AreaPath } from "../models/areaPath";

const PAGE_SIZE = 50;

export default function WorkItemsListPage() {
  const [areaPaths, setAreaPaths] = useState<AreaPath[]>([]);
  const [items, setItems] = useState<WorkItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [areaPathId, setAreaPathId] = useState<number | undefined>(undefined);
  const [workItemType, setWorkItemType] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAreaPaths()
      .then(setAreaPaths)
      .catch(() => {
        /* area path filter is optional; a failure here just leaves the dropdown empty */
      });
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchWorkItems({
      areaPathId,
      workItemType: workItemType || undefined,
      page,
      pageSize: PAGE_SIZE,
    })
      .then((response) => {
        setItems(response.data);
        setTotal(response.pagination.total);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [areaPathId, workItemType, page]);

  return (
    <Card>
      <HStack gap={4} align="end" wrap="wrap">
        <Selector
          label="Area path"
          hasSearch
          hasClear
          value={areaPathId !== undefined ? String(areaPathId) : null}
          onChange={(value) => {
            setPage(1);
            setAreaPathId(value ? Number(value) : undefined);
          }}
          options={areaPaths.map((ap) => ({
            value: String(ap.id),
            label: ap.area_path,
          }))}
          placeholder="All"
          width={280}
        />
        <TextInput
          label="Type"
          hasClear
          value={workItemType}
          onChange={(value) => {
            setPage(1);
            setWorkItemType(value);
          }}
          placeholder="e.g. Bug"
          width={200}
        />
      </HStack>

      {error && (
        <Banner status="error" title="Error loading work items" description={error} />
      )}

      {loading && !error && <Spinner label="Loading work items" />}

      {!loading && !error && items.length === 0 && (
        <EmptyState
          title="No work items found"
          description="Try adjusting the area path or type filter."
        />
      )}

      {!loading && !error && items.length > 0 && (
        <>
          <Table
            data={items as unknown as Record<string, unknown>[]}
            idKey="id"
            density="balanced"
            dividers="rows"
            hasHover
            columns={[
              { key: "id", header: "ID", width: pixel(80) },
              { key: "title", header: "Title", width: proportional(3) },
              { key: "work_item_type", header: "Type", width: proportional(1) },
              {
                key: "state",
                header: "State",
                width: proportional(1),
                renderCell: (item: Record<string, unknown>) => (
                  <Badge label={(item.state as string | null) ?? "—"} />
                ),
              },
              { key: "assigned_to", header: "Assigned To", width: proportional(1) },
              { key: "changed_date", header: "Changed Date", width: proportional(1) },
            ]}
          />

          <Pagination
            variant="compact"
            page={page}
            onChange={setPage}
            totalItems={total}
            pageSize={PAGE_SIZE}
          />
        </>
      )}
    </Card>
  );
}
