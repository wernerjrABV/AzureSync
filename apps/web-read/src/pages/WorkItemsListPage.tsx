import { useEffect, useState } from "react";
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

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div>
      <h1>Work Items</h1>

      <div>
        <label>
          Area path:{" "}
          <select
            value={areaPathId ?? ""}
            onChange={(e) => {
              setPage(1);
              setAreaPathId(e.target.value ? Number(e.target.value) : undefined);
            }}
          >
            <option value="">All</option>
            {areaPaths.map((ap) => (
              <option key={ap.id} value={ap.id}>
                {ap.area_path}
              </option>
            ))}
          </select>
        </label>
        {"  "}
        <label>
          Type:{" "}
          <input
            value={workItemType}
            onChange={(e) => {
              setPage(1);
              setWorkItemType(e.target.value);
            }}
            placeholder="e.g. Bug"
          />
        </label>
      </div>

      {error && <p role="alert">Error loading work items: {error}</p>}

      {loading && !error && <p>Loading...</p>}

      {!loading && !error && items.length === 0 && <p>No work items found.</p>}

      {!loading && !error && items.length > 0 && (
        <>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Title</th>
                <th>Type</th>
                <th>State</th>
                <th>Assigned To</th>
                <th>Changed Date</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{item.id}</td>
                  <td>{item.title}</td>
                  <td>{item.work_item_type}</td>
                  <td>{item.state}</td>
                  <td>{item.assigned_to}</td>
                  <td>{item.changed_date}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div>
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </button>
            <span>
              {" "}
              Page {page} of {totalPages} ({total} total){" "}
            </span>
            <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
