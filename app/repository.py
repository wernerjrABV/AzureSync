import psycopg
from psycopg.rows import dict_row


def create_area_path(
    conn: psycopg.Connection,
    organization: str,
    project: str,
    area_path: str,
    incluir_subpaths: bool = True,
    ativo: bool = True,
    intervalo_minutos: int = 60,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO area_paths
                (organization, project, area_path, incluir_subpaths, ativo, intervalo_minutos)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (organization, project, area_path, incluir_subpaths, ativo, intervalo_minutos),
        )
        return cur.fetchone()[0]


def list_area_paths(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM area_paths ORDER BY id")
        return cur.fetchall()


def get_area_path(conn: psycopg.Connection, area_path_id: int) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM area_paths WHERE id = %s", (area_path_id,))
        return cur.fetchone()


def update_area_path(conn: psycopg.Connection, area_path_id: int, **fields) -> None:
    if not fields:
        return
    columns = ", ".join(f"{key} = %s" for key in fields)
    values = list(fields.values()) + [area_path_id]
    with conn.cursor() as cur:
        cur.execute(f"UPDATE area_paths SET {columns} WHERE id = %s", values)


def delete_area_path(conn: psycopg.Connection, area_path_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sync_logs WHERE area_path_id = %s", (area_path_id,))
        cur.execute("DELETE FROM sync_checkpoints WHERE area_path_id = %s", (area_path_id,))
        cur.execute("DELETE FROM work_items WHERE area_path_id = %s", (area_path_id,))
        cur.execute("DELETE FROM area_paths WHERE id = %s", (area_path_id,))


def try_acquire_lock(conn: psycopg.Connection, area_path_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE area_paths SET is_running = TRUE WHERE id = %s AND is_running = FALSE RETURNING id",
            (area_path_id,),
        )
        return cur.fetchone() is not None


def release_lock(conn: psycopg.Connection, area_path_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE area_paths SET is_running = FALSE WHERE id = %s", (area_path_id,))


def update_sync_result(conn: psycopg.Connection, area_path_id: int, status: str, count: int, synced_at) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE area_paths
            SET last_sync_status = %s, last_sync_count = %s, last_sync_at = %s
            WHERE id = %s
            """,
            (status, count, synced_at, area_path_id),
        )


def get_checkpoint(conn: psycopg.Connection, area_path_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_changed_date FROM sync_checkpoints WHERE area_path_id = %s",
            (area_path_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def set_checkpoint(conn: psycopg.Connection, area_path_id: int, changed_date) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sync_checkpoints (area_path_id, last_changed_date)
            VALUES (%s, %s)
            ON CONFLICT (area_path_id) DO UPDATE SET last_changed_date = EXCLUDED.last_changed_date
            """,
            (area_path_id, changed_date),
        )


def get_work_item_ids(conn: psycopg.Connection, area_path_id: int) -> set[int]:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM work_items WHERE area_path_id = %s", (area_path_id,))
        return {row[0] for row in cur.fetchall()}


def upsert_work_items(conn: psycopg.Connection, area_path_id: int, items: list[dict]) -> None:
    if not items:
        return
    with conn.cursor() as cur:
        for item in items:
            cur.execute(
                """
                INSERT INTO work_items
                    (id, area_path_id, title, work_item_type, state, assigned_to, changed_date, raw_json, synced_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (id) DO UPDATE SET
                    area_path_id = EXCLUDED.area_path_id,
                    title = EXCLUDED.title,
                    work_item_type = EXCLUDED.work_item_type,
                    state = EXCLUDED.state,
                    assigned_to = EXCLUDED.assigned_to,
                    changed_date = EXCLUDED.changed_date,
                    raw_json = EXCLUDED.raw_json,
                    synced_at = now()
                """,
                (
                    item["id"],
                    area_path_id,
                    item["title"],
                    item["work_item_type"],
                    item["state"],
                    item["assigned_to"],
                    item["changed_date"],
                    item["raw_json"],
                ),
            )


def delete_work_items(conn: psycopg.Connection, area_path_id: int, ids: set[int]) -> None:
    if not ids:
        return
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM work_items WHERE area_path_id = %s AND id = ANY(%s)",
            (area_path_id, list(ids)),
        )


def create_sync_log(conn: psycopg.Connection, area_path_id: int, started_at) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO sync_logs (area_path_id, started_at) VALUES (%s, %s) RETURNING id",
            (area_path_id, started_at),
        )
        return cur.fetchone()[0]


def finish_sync_log(
    conn: psycopg.Connection,
    log_id: int,
    finished_at,
    status: str,
    items_processed: int,
    error_msg: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE sync_logs
            SET finished_at = %s, status = %s, items_processed = %s, error_msg = %s
            WHERE id = %s
            """,
            (finished_at, status, items_processed, error_msg, log_id),
        )
