import { useEffect, useRef, useState } from "react";
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

type WorkItemRow = WorkItem & Record<string, unknown>;

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 350;
const SEARCH_MIN_LENGTH = 3;

export default function WorkItemsListPage() {
  const [areaPaths, setAreaPaths] = useState<AreaPath[]>([]);
  const [areaPathsLoaded, setAreaPathsLoaded] = useState(false);
  const [items, setItems] = useState<WorkItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [areaPathId, setAreaPathId] = useState<number | undefined>(undefined);
  const [searchInput, setSearchInput] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const latestRequestId = useRef(0);

  useEffect(() => {
    const handle = setTimeout(() => {
      if (searchInput.length === 0 || searchInput.length >= SEARCH_MIN_LENGTH) {
        setPage(1);
        setSearch(searchInput);
      }
    }, SEARCH_DEBOUNCE_MS);

    return () => clearTimeout(handle);
  }, [searchInput]);

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
    const requestId = ++latestRequestId.current;
    setLoading(true);
    setError(null);
    fetchWorkItems({
      areaPathId,
      search: search || undefined,
      page,
      pageSize: PAGE_SIZE,
    })
      .then((response) => {
        if (requestId !== latestRequestId.current) {
          return;
        }
        setItems(response.data);
        setTotal(response.pagination.total);
      })
      .catch((err: Error) => {
        if (requestId === latestRequestId.current) {
          setError(err.message);
        }
      })
      .finally(() => {
        if (requestId === latestRequestId.current) {
          setLoading(false);
        }
      });
  }, [areaPathId, search, page]);

  return (
    <Card>
      <HStack gap={4} align="end" wrap="wrap">
        <Selector
          label="Area path"
          hasSearch
          value={areaPathId !== undefined ? String(areaPathId) : undefined}
          onChange={(value) => {
            setPage(1);
            setAreaPathId(value ? Number(value) : undefined);
          }}
          options={areaPaths.map((ap) => ({
            value: String(ap.id),
            label: ap.area_path,
          }))}
          width={280}
        />
        <TextInput
          label="Search"
          hasClear
          value={searchInput}
          onChange={setSearchInput}
          placeholder="Search by id, title, type, state, assigned to (min. 3 characters)"
          width={320}
        />
      </HStack>

      {error && (
        <Banner status="error" title="Error loading work items" description={error} />
      )}

      {areaPathsLoaded && areaPaths.length === 0 && (
        <EmptyState
          title="No area paths configured"
          description="Configure at least one area path in the sync service to see work items."
        />
      )}

      {!areaPathsLoaded && (
        <Spinner label="Loading area paths" />
      )}

      {areaPathId !== undefined && loading && !error && (
        <Spinner label="Loading work items" />
      )}

      {areaPathId !== undefined && !loading && !error && items.length === 0 && (
        <EmptyState
          title="No work items found"
          description="Try adjusting the search."
        />
      )}

      {areaPathId !== undefined && !loading && !error && items.length > 0 && (
        <>
          <Table
            data={items as WorkItemRow[]}
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
                renderCell: (item: WorkItemRow) => (
                  <Badge label={item.state ?? "—"} />
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
