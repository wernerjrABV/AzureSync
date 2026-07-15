import datetime

from app import repository as repo
from app.ado_client import AdoAuthError, AdoClient, AdoRetryExhaustedError


def run_sync(conn, area_path_row: dict, client: AdoClient) -> dict:
    area_path_id = area_path_row["id"]

    if not repo.try_acquire_lock(conn, area_path_id):
        return {"status": "skipped_running", "items_processed": 0}
    conn.commit()

    started_at = datetime.datetime.now()
    log_id = repo.create_sync_log(conn, area_path_id, started_at)
    conn.commit()

    try:
        items_processed = _do_sync(conn, area_path_row, client)
        finished_at = datetime.datetime.now()
        repo.finish_sync_log(conn, log_id, finished_at, status="ok", items_processed=items_processed)
        repo.update_sync_result(conn, area_path_id, status="ok", count=items_processed, synced_at=finished_at)
        conn.commit()
        return {"status": "ok", "items_processed": items_processed}

    except AdoAuthError as exc:
        return _fail(conn, area_path_id, log_id, "auth_error", str(exc))

    except AdoRetryExhaustedError as exc:
        return _fail(conn, area_path_id, log_id, "error", str(exc))

    except Exception as exc:  # unexpected error: still release lock and record it
        return _fail(conn, area_path_id, log_id, "error", str(exc))

    finally:
        repo.release_lock(conn, area_path_id)
        conn.commit()


def _do_sync(conn, area_path_row: dict, client: AdoClient) -> int:
    area_path_id = area_path_row["id"]
    area_path = area_path_row["area_path"]
    incluir_subpaths = area_path_row["incluir_subpaths"]

    current_ids = set(client.get_all_ids(area_path, incluir_subpaths))

    checkpoint = repo.get_checkpoint(conn, area_path_id)
    changed_ids = client.get_changed_ids(area_path, incluir_subpaths, since=checkpoint)

    items = client.get_work_items_batch(changed_ids)
    repo.upsert_work_items(conn, area_path_id, items)

    stored_ids = repo.get_work_item_ids(conn, area_path_id)
    removed_ids = stored_ids - current_ids
    repo.delete_work_items(conn, area_path_id, removed_ids)

    if items:
        max_changed_date = max(item["changed_date"] for item in items if item["changed_date"])
        repo.set_checkpoint(conn, area_path_id, max_changed_date)

    return len(items)


def _fail(conn, area_path_id: int, log_id: int, status: str, error_msg: str) -> dict:
    finished_at = datetime.datetime.now()
    repo.finish_sync_log(conn, log_id, finished_at, status=status, items_processed=0, error_msg=error_msg)
    repo.update_sync_result(conn, area_path_id, status=status, count=0, synced_at=finished_at)
    conn.commit()
    return {"status": status, "items_processed": 0}
