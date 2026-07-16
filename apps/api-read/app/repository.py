"""Read-only query layer for apps/api-read.

This module must contain only SELECT queries. apps/sync-service is the only
writer to this database (see docs/adr/0002-single-writer.md and
docs/adr/0003-read-only-api.md). This constraint is enforced mechanically by
tests/test_readonly_guardrail.py.
"""

import psycopg
from psycopg.rows import dict_row

_ORDER_BY_COLUMNS = {"changed_date", "id", "title"}
_ORDER_DIRS = {"asc", "desc"}


class InvalidQueryParam(ValueError):
    pass


def list_area_paths(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id, organization, project, area_path FROM area_paths ORDER BY id"
        )
        return cur.fetchall()


def list_work_items(
    conn: psycopg.Connection,
    *,
    area_path_id: int | None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
    order_by: str = "changed_date",
    order_dir: str = "desc",
) -> tuple[list[dict], int]:
    if area_path_id is None:
        raise InvalidQueryParam("area_path_id is required")
    if order_by not in _ORDER_BY_COLUMNS:
        raise InvalidQueryParam(f"invalid order_by: {order_by}")
    if order_dir not in _ORDER_DIRS:
        raise InvalidQueryParam(f"invalid order_dir: {order_dir}")
    if page < 1:
        raise InvalidQueryParam("page must be >= 1")
    if page_size < 1 or page_size > 200:
        raise InvalidQueryParam("page_size must be between 1 and 200")

    where_clauses = ["area_path_id = %s"]
    params: list = [area_path_id]

    search = (search or "").strip()
    if search:
        # Known, accepted limitation: literal % or _ typed by the user act as
        # ILIKE wildcards (e.g. "50_" also matches "501"). Not a security
        # issue (query is parameterized) — deliberately not escaped here.
        pattern = f"%{search}%"
        where_clauses.append(
            "(id::text ILIKE %s OR title ILIKE %s OR work_item_type ILIKE %s "
            "OR state ILIKE %s OR assigned_to ILIKE %s)"
        )
        params.extend([pattern, pattern, pattern, pattern, pattern])

    where_sql = f"WHERE {' AND '.join(where_clauses)}"

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT COUNT(*) AS total FROM work_items {where_sql}", params)
        total = cur.fetchone()["total"]

        offset = (page - 1) * page_size
        cur.execute(
            f"""
            SELECT id, area_path_id, title, work_item_type, state, assigned_to,
                   changed_date, parent_id
            FROM work_items
            {where_sql}
            ORDER BY {order_by} {order_dir}
            LIMIT %s OFFSET %s
            """,
            params + [page_size, offset],
        )
        rows = cur.fetchall()

    return rows, total


def list_features_tree(conn: psycopg.Connection, *, area_path_id: int) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, title, work_item_type, parent_id, start_date, target_date
            FROM work_items AS w
            WHERE area_path_id = %s
              AND work_item_type IN ('Feature', 'Epic', 'Solution')
              AND (state IS NULL OR state NOT IN ('Cancelled', 'Canceled', 'Removed'))
              AND NOT (
                -- Closed Solutions with no linked Feature (direct or via an Epic)
                work_item_type = 'Solution'
                AND state = 'Closed'
                AND NOT EXISTS (
                    SELECT 1 FROM work_items AS f
                    WHERE f.area_path_id = w.area_path_id
                      AND f.work_item_type = 'Feature'
                      AND (f.state IS NULL OR f.state NOT IN ('Cancelled', 'Canceled', 'Removed'))
                      AND (
                        f.parent_id = w.id
                        OR f.parent_id IN (
                            SELECT e.id FROM work_items AS e
                            WHERE e.parent_id = w.id AND e.work_item_type = 'Epic'
                        )
                      )
                )
              )
              AND NOT (
                -- Epics whose parent Solution is excluded by the rule above would
                -- otherwise be orphaned as a meaningless top-level node.
                work_item_type = 'Epic'
                AND EXISTS (
                    SELECT 1 FROM work_items AS sol
                    WHERE sol.id = w.parent_id
                      AND sol.work_item_type = 'Solution'
                      AND sol.state = 'Closed'
                      AND NOT EXISTS (
                          SELECT 1 FROM work_items AS f
                          WHERE f.area_path_id = sol.area_path_id
                            AND f.work_item_type = 'Feature'
                            AND (f.state IS NULL OR f.state NOT IN ('Cancelled', 'Canceled', 'Removed'))
                            AND (
                              f.parent_id = sol.id
                              OR f.parent_id IN (
                                  SELECT e.id FROM work_items AS e
                                  WHERE e.parent_id = sol.id AND e.work_item_type = 'Epic'
                              )
                            )
                      )
                )
              )
            ORDER BY id
            """,
            (area_path_id,),
        )
        return cur.fetchall()
