import datetime

from app import repository as repo
from app.ado_client import AdoAuthError, AdoClient, AdoRetryExhaustedError
from app.capacity import StatusInterval, build_capacity_snapshot, build_status_intervals

# Commit periodically during the per-item history backfill so a first-load sync over
# thousands of work items doesn't hold one long-lived Postgres transaction open
# (idle-in-transaction / lock retention risk). Value is arbitrary but small enough to
# bound transaction length while still batching most commit overhead away.
HISTORY_COMMIT_BATCH_SIZE = 50


class SyncCancelled(Exception):
    """Raised when a user requests cancellation of an active synchronization."""


def run_sync(conn, area_path_row: dict, client: AdoClient, should_cancel=None) -> dict:
    area_path_id = area_path_row["id"]

    if not repo.try_acquire_lock(conn, area_path_id):
        return {"status": "skipped_running", "items_processed": 0}
    conn.commit()

    started_at = datetime.datetime.now()
    log_id = repo.create_sync_log(conn, area_path_id, started_at)
    conn.commit()

    try:
        items_processed = _do_sync(conn, area_path_row, client, should_cancel=should_cancel)
        finished_at = datetime.datetime.now()
        repo.finish_sync_log(conn, log_id, finished_at, status="ok", items_processed=items_processed)
        repo.update_sync_result(
            conn, area_path_id, status="ok", count=items_processed, synced_at=finished_at, error_msg=None
        )
        conn.commit()
        return {"status": "ok", "items_processed": items_processed}

    except AdoAuthError as exc:
        return _fail(conn, area_path_id, log_id, "auth_error", str(exc))

    except AdoRetryExhaustedError as exc:
        return _fail(conn, area_path_id, log_id, "error", str(exc))

    except SyncCancelled:
        return _fail(conn, area_path_id, log_id, "cancelled", "Synchronization cancelled by user.")

    except Exception as exc:  # unexpected error: still release lock and record it
        return _fail(conn, area_path_id, log_id, "error", str(exc))

    finally:
        repo.release_lock(conn, area_path_id)
        conn.commit()


def _check_cancelled(should_cancel) -> None:
    if should_cancel is not None and should_cancel():
        raise SyncCancelled


def _do_sync(conn, area_path_row: dict, client: AdoClient, should_cancel=None) -> int:
    area_path_id = area_path_row["id"]
    area_path = area_path_row["area_path"]
    incluir_subpaths = area_path_row["incluir_subpaths"]

    _check_cancelled(should_cancel)
    current_ids = set(client.get_all_ids(area_path, incluir_subpaths))

    _check_cancelled(should_cancel)
    checkpoint = repo.get_checkpoint(conn, area_path_id)
    changed_ids = client.get_changed_ids(area_path, incluir_subpaths, since=checkpoint)

    _check_cancelled(should_cancel)
    items = client.get_work_items_batch(changed_ids)
    repo.upsert_work_items(conn, area_path_id, items)

    stored_ids = repo.get_work_item_ids(conn, area_path_id)
    removed_ids = stored_ids - current_ids
    repo.delete_work_items(conn, area_path_id, removed_ids)

    if items:
        max_changed_date = max(item["changed_date"] for item in items if item["changed_date"])
        repo.set_checkpoint(conn, area_path_id, max_changed_date)

    is_first_history_load = repo.get_history_loaded_at(conn, area_path_id) is None
    history_target_ids = current_ids if is_first_history_load else set(changed_ids)
    any_history_failed = False
    for processed_count, work_item_id in enumerate(history_target_ids, start=1):
        _check_cancelled(should_cancel)
        try:
            updates = client.get_work_item_updates(work_item_id)
            repo.upsert_work_item_history(conn, area_path_id, work_item_id, updates)
            work_item_type = repo.get_work_item_type(conn, work_item_id=work_item_id)
            if work_item_type is None:
                # Keep the last known interval projection in place. Replacing it with
                # an empty projection would make the capacity data silently incomplete;
                # treating this as a per-item history failure also retains the snapshot.
                any_history_failed = True
            else:
                intervals = build_status_intervals(
                    work_item_id=work_item_id,
                    area_path_id=area_path_id,
                    work_item_type=work_item_type,
                    updates=repo.load_work_item_history(conn, work_item_id=work_item_id),
                )
                repo.replace_work_item_status_intervals(
                    conn,
                    work_item_id=work_item_id,
                    area_path_id=area_path_id,
                    intervals=intervals,
                )
        except AdoAuthError:
            # bad credentials will fail identically for every remaining item; let it
            # propagate so run_sync reports auth_error and stops the sync immediately.
            raise
        except Exception:
            # one poisoned item (e.g. AdoRetryExhaustedError from a permanently-erroring
            # work item) must not stall history sync for every other item, nor abort the
            # checkpoint/upsert/delete work already completed above (Finding 1).
            any_history_failed = True

        if processed_count % HISTORY_COMMIT_BATCH_SIZE == 0:
            conn.commit()

        _check_cancelled(should_cancel)

    if is_first_history_load and not any_history_failed:
        repo.set_history_loaded(conn, area_path_id, datetime.datetime.now())

    if not any_history_failed:
        _check_cancelled(should_cancel)
        generated_at = datetime.datetime.now()
        snapshot = build_capacity_snapshot(
            area_path_id=area_path_id,
            intervals=[
                StatusInterval(**interval)
                for interval in repo.load_capacity_intervals(conn, area_path_id=area_path_id)
            ],
            as_of=generated_at,
        )
        repo.upsert_capacity_snapshot(
            conn,
            area_path_id=area_path_id,
            payload=snapshot,
            generated_at=generated_at,
        )

    return len(items)


def _fail(conn, area_path_id: int, log_id: int, status: str, error_msg: str) -> dict:
    conn.rollback()  # _do_sync may have left the transaction aborted; further writes need a clean slate
    finished_at = datetime.datetime.now()
    repo.finish_sync_log(conn, log_id, finished_at, status=status, items_processed=0, error_msg=error_msg)
    repo.update_sync_result(conn, area_path_id, status=status, count=0, synced_at=finished_at, error_msg=error_msg)
    conn.commit()
    return {"status": status, "items_processed": 0}
