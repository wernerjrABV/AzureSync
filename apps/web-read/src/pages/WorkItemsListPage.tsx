import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Card } from "@astryxdesign/core/Layout";
import { HStack, VStack } from "@astryxdesign/core/Layout";
import { Selector } from "@astryxdesign/core/Selector";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Table, proportional, pixel } from "@astryxdesign/core/Table";
import type { TablePlugin } from "@astryxdesign/core/Table";
import { Pagination } from "@astryxdesign/core/Pagination";
import { Banner } from "@astryxdesign/core/Banner";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Badge } from "@astryxdesign/core/Badge";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { Text } from "@astryxdesign/core/Text";
import { fetchWorkItemDetails, fetchWorkItems, fetchAreaPaths } from "../services/apiReadClient";
import type { WorkItem, WorkItemDetails } from "../models/workItem";
import type { AreaPath } from "../models/areaPath";

type WorkItemRow = WorkItem & Record<string, unknown>;

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 350;
const SEARCH_MIN_LENGTH = 3;

function displayDetailValue(value: string | number | null): string {
  return value === null ? "—" : String(value);
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? "—";
}

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
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);
  const [details, setDetails] = useState<WorkItemDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState<string | null>(null);
  const latestRequestId = useRef(0);
  const latestDetailsRequestId = useRef(0);

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

  const handleRowClick = useCallback((id: number) => {
    const requestId = ++latestDetailsRequestId.current;
    setSelectedItemId(id);
    setDetails(null);
    setDetailsError(null);
    setDetailsLoading(true);
    fetchWorkItemDetails(id)
      .then((response) => {
        if (requestId === latestDetailsRequestId.current) {
          setDetails(response);
        }
      })
      .catch((err: Error) => {
        if (requestId === latestDetailsRequestId.current) {
          setDetailsError(err.message);
        }
      })
      .finally(() => {
        if (requestId === latestDetailsRequestId.current) {
          setDetailsLoading(false);
        }
      });
  }, []);

  const closeDetails = useCallback(() => {
    ++latestDetailsRequestId.current;
    setSelectedItemId(null);
    setDetails(null);
    setDetailsError(null);
    setDetailsLoading(false);
  }, []);

  const rowClickPlugin = useMemo<TablePlugin<WorkItemRow>>(
    () => ({
      transformBodyRow: (props, item) => ({
        ...props,
        htmlProps: {
          ...props.htmlProps,
          onClick: () => handleRowClick(item.id),
        },
      }),
    }),
    [handleRowClick],
  );

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
            plugins={{ rowClick: rowClickPlugin }}
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

      <Dialog
        isOpen={selectedItemId !== null}
        onOpenChange={(isOpen) => !isOpen && closeDetails()}
        width={630}
        maxHeight="100vh"
        position={{ top: 0, right: 0, bottom: 0 }}
      >
        <DialogHeader
          title="Work item details"
          onOpenChange={(isOpen) => !isOpen && closeDetails()}
        />
        {detailsLoading && <Spinner label="Loading work item details" />}
        {detailsError && (
          <Banner
            status="error"
            title="Error loading work item details"
            description={detailsError}
          />
        )}
        {details && (
          <VStack gap={4}>
            <VStack gap={2}>
              <Text as="div" weight="semibold">Current fields</Text>
              <Text>ID: {String(details.item.id)}</Text>
              <Text>Title: {displayDetailValue(details.item.title)}</Text>
              <Text>Area path ID: {String(details.item.area_path_id)}</Text>
              <Text>Work item type: {displayDetailValue(details.item.work_item_type)}</Text>
              <Text>State: {displayDetailValue(details.item.state)}</Text>
              <Text>Assigned to: {displayDetailValue(details.item.assigned_to)}</Text>
              <Text>Changed date: {displayDetailValue(details.item.changed_date)}</Text>
              <Text>Parent ID: {displayDetailValue(details.item.parent_id)}</Text>
              <Text>Synced at: {displayDetailValue(details.item.synced_at)}</Text>
              <Text>Start date: {displayDetailValue(details.item.start_date)}</Text>
              <Text>Target date: {displayDetailValue(details.item.target_date)}</Text>
              <Text>Created date: {displayDetailValue(details.item.created_date)}</Text>
              <Text>Activated date: {displayDetailValue(details.item.activated_date)}</Text>
              <Text>Closed date: {displayDetailValue(details.item.closed_date)}</Text>
            </VStack>

            <VStack gap={2}>
              <Text as="div" weight="semibold">Raw JSON</Text>
              <Text as="div" type="code">{formatJson(details.item.raw_json)}</Text>
            </VStack>

            <VStack gap={3}>
              <Text as="div" weight="semibold">History</Text>
              {details.history.map((revision) => (
                <VStack key={`${revision.work_item_id}-${revision.rev}`} gap={2}>
                  <Text as="div" weight="semibold">Revision {String(revision.rev)}</Text>
                  <Text>Revised by: {displayDetailValue(revision.revised_by)}</Text>
                  <Text>Revised date: {displayDetailValue(revision.revised_date)}</Text>
                  <Text>Synced at: {displayDetailValue(revision.synced_at)}</Text>
                  <Text as="div" type="code">{formatJson(revision.raw_json)}</Text>
                </VStack>
              ))}
            </VStack>
          </VStack>
        )}
      </Dialog>
    </Card>
  );
}
