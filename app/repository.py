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
