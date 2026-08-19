import datetime
import json
import base64
import binascii

import psycopg
from psycopg.rows import dict_row

from app.capacity import StatusInterval

APP_SETTING_CREDENTIAL_KEY = "azure_devops_api_key"
# Plaintext PATs are capped separately at 4096 characters in credentials.py.
# Stored ciphertext is Base64-encoded DPAPI output, so it needs headroom for
# encryption metadata plus Base64 expansion while still remaining bounded.
APP_SETTING_ENCRYPTED_VALUE_MAX_LENGTH = 16384


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
        cur.execute("DELETE FROM capacity_snapshots WHERE area_path_id = %s", (area_path_id,))
        cur.execute("DELETE FROM work_item_status_intervals WHERE area_path_id = %s", (area_path_id,))
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


def update_sync_result(
    conn: psycopg.Connection,
    area_path_id: int,
    status: str,
    count: int,
    synced_at,
    error_msg: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE area_paths
            SET last_sync_status = %s, last_sync_count = %s, last_sync_at = %s, last_error_msg = %s
            WHERE id = %s
            """,
            (status, count, synced_at, error_msg, area_path_id),
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
                    (id, area_path_id, title, work_item_type, state, assigned_to, changed_date,
                     start_date, target_date, created_date, activated_date, closed_date,
                     parent_id, raw_json, synced_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (id) DO UPDATE SET
                    area_path_id = EXCLUDED.area_path_id,
                    title = EXCLUDED.title,
                    work_item_type = EXCLUDED.work_item_type,
                    state = EXCLUDED.state,
                    assigned_to = EXCLUDED.assigned_to,
                    changed_date = EXCLUDED.changed_date,
                    start_date = EXCLUDED.start_date,
                    target_date = EXCLUDED.target_date,
                    created_date = EXCLUDED.created_date,
                    activated_date = EXCLUDED.activated_date,
                    closed_date = EXCLUDED.closed_date,
                    parent_id = EXCLUDED.parent_id,
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
                    item.get("start_date"),
                    item.get("target_date"),
                    item.get("created_date"),
                    item.get("activated_date"),
                    item.get("closed_date"),
                    item.get("parent_id"),
                    item["raw_json"],
                ),
            )


def delete_work_items(conn: psycopg.Connection, area_path_id: int, ids: set[int]) -> None:
    if not ids:
        return
    with conn.cursor() as cur:
        if getattr(conn, "is_sqlite", False):
            marks = ",".join("%s" for _ in ids)
            cur.execute(
                f"DELETE FROM work_item_status_intervals WHERE area_path_id = %s AND work_item_id IN ({marks})",
                [area_path_id, *ids],
            )
            cur.execute(f"DELETE FROM work_items WHERE area_path_id = %s AND id IN ({marks})", [area_path_id, *ids])
        else:
            cur.execute(
                "DELETE FROM work_item_status_intervals WHERE area_path_id = %s AND work_item_id = ANY(%s)",
                (area_path_id, list(ids)),
            )
            cur.execute("DELETE FROM work_items WHERE area_path_id = %s AND id = ANY(%s)", (area_path_id, list(ids)))


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


def _parse_revised_date(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    return datetime.datetime.strptime(value.split(".")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S")


def upsert_work_item_history(
    conn: psycopg.Connection, area_path_id: int, work_item_id: int, updates: list[dict]
) -> None:
    if not updates:
        return
    with conn.cursor() as cur:
        for update in updates:
            revised_by_field = update.get("revisedBy")
            revised_by = (
                revised_by_field.get("uniqueName")
                if isinstance(revised_by_field, dict)
                else revised_by_field
            )
            cur.execute(
                """
                INSERT INTO work_item_history
                    (work_item_id, area_path_id, rev, revised_by, revised_date, raw_json, synced_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (work_item_id, rev) DO UPDATE SET
                    area_path_id = EXCLUDED.area_path_id,
                    revised_by = EXCLUDED.revised_by,
                    revised_date = EXCLUDED.revised_date,
                    raw_json = EXCLUDED.raw_json,
                    synced_at = now()
                """,
                (
                    work_item_id,
                    area_path_id,
                    update["rev"],
                    revised_by,
                    _parse_revised_date(update.get("revisedDate")),
                    json.dumps(update),
                ),
            )


def load_work_item_history(conn: psycopg.Connection, *, work_item_id: int) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT raw_json FROM work_item_history WHERE work_item_id = %s ORDER BY rev",
            (work_item_id,),
        )
        rows = cur.fetchall()

    updates = []
    for row in rows:
        raw_json = row["raw_json"]
        updates.append(json.loads(raw_json) if isinstance(raw_json, str) else raw_json)
    return updates


def get_work_item_type(conn: psycopg.Connection, *, work_item_id: int) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT work_item_type FROM work_items WHERE id = %s", (work_item_id,))
        row = cur.fetchone()
        return row[0] if row else None


def replace_work_item_status_intervals(
    conn: psycopg.Connection,
    *,
    work_item_id: int,
    area_path_id: int,
    intervals: list[StatusInterval],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM work_item_status_intervals WHERE work_item_id = %s AND area_path_id = %s",
            (work_item_id, area_path_id),
        )
        for interval in intervals:
            cur.execute(
                """
                INSERT INTO work_item_status_intervals
                    (work_item_id, area_path_id, revision, work_item_type, state, started_at, ended_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    work_item_id,
                    area_path_id,
                    interval.revision,
                    interval.work_item_type,
                    interval.state,
                    interval.started_at,
                    interval.ended_at,
                ),
            )


def load_capacity_intervals(conn: psycopg.Connection, *, area_path_id: int) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT work_item_id, area_path_id, revision, work_item_type, state, started_at, ended_at
            FROM work_item_status_intervals
            WHERE area_path_id = %s
            ORDER BY work_item_id, revision
            """,
            (area_path_id,),
        )
        return cur.fetchall()


def upsert_capacity_snapshot(
    conn: psycopg.Connection,
    *,
    area_path_id: int,
    payload: dict,
    generated_at: datetime.datetime,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO capacity_snapshots (area_path_id, generated_at, payload)
            VALUES (%s, %s, %s)
            ON CONFLICT (area_path_id) DO UPDATE SET
                generated_at = EXCLUDED.generated_at,
                payload = EXCLUDED.payload
            """,
            (area_path_id, generated_at, json.dumps(payload)),
        )


def get_capacity_snapshot(conn: psycopg.Connection, *, area_path_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT payload FROM capacity_snapshots WHERE area_path_id = %s", (area_path_id,))
        row = cur.fetchone()

    if row is None:
        return None
    payload = row[0]
    return json.loads(payload) if isinstance(payload, str) else payload


def set_history_loaded(conn: psycopg.Connection, area_path_id: int, when) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE area_paths SET history_loaded_at = %s WHERE id = %s", (when, area_path_id)
        )


def get_history_loaded_at(conn: psycopg.Connection, area_path_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT history_loaded_at FROM area_paths WHERE id = %s", (area_path_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None


def get_app_setting(conn: psycopg.Connection, key: str) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT key, encrypted_value, updated_at FROM app_settings WHERE key = %s",
            (key,),
        )
        return cur.fetchone()


def upsert_app_setting(
    conn: psycopg.Connection,
    *,
    key: str,
    encrypted_value: str,
    updated_at: datetime.datetime,
) -> None:
    _validate_app_setting(key=key, encrypted_value=encrypted_value)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO app_settings (key, encrypted_value, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (key) DO UPDATE SET
                encrypted_value = EXCLUDED.encrypted_value,
                updated_at = EXCLUDED.updated_at
            """,
            (key, encrypted_value, updated_at),
        )


def delete_app_setting(conn: psycopg.Connection, key: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM app_settings WHERE key = %s", (key,))


def _validate_app_setting(*, key: str, encrypted_value: str) -> None:
    if key != APP_SETTING_CREDENTIAL_KEY:
        raise ValueError(
            "app setting key must be 'azure_devops_api_key'"
        )
    if len(encrypted_value) > APP_SETTING_ENCRYPTED_VALUE_MAX_LENGTH:
        raise ValueError(
            "app setting encrypted_value must be at most 16384 characters"
        )
    if not _is_strict_base64(encrypted_value):
        raise ValueError(
            "app setting encrypted_value must be non-empty Base64"
        )


def _is_strict_base64(value: str) -> bool:
    if not value:
        return False
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return False
    return bool(decoded) and base64.b64encode(decoded).decode("ascii") == value
