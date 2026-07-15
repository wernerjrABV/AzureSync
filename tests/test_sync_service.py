import datetime
from unittest.mock import MagicMock, patch

import psycopg

from app import repository as repo
from app import sync_service
from app.ado_client import AdoAuthError, AdoRetryExhaustedError


def _area_path_row(db_conn, incluir_subpaths=True):
    area_path_id = repo.create_area_path(
        db_conn, "org", "proj", "proj\\A", incluir_subpaths=incluir_subpaths
    )
    db_conn.commit()
    return repo.get_area_path(db_conn, area_path_id)


def test_full_load_upserts_all_items_and_sets_checkpoint(db_conn):
    row = _area_path_row(db_conn)
    client = MagicMock()
    client.get_all_ids.return_value = [1, 2]
    client.get_changed_ids.return_value = [1, 2]
    client.get_work_items_batch.return_value = [
        {
            "id": 1,
            "title": "A",
            "work_item_type": "Bug",
            "state": "Active",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 1),
            "raw_json": "{}",
        },
        {
            "id": 2,
            "title": "B",
            "work_item_type": "Task",
            "state": "New",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 2),
            "raw_json": "{}",
        },
    ]

    result = sync_service.run_sync(db_conn, row, client)
    db_conn.commit()

    assert result["status"] == "ok"
    assert result["items_processed"] == 2
    assert repo.get_work_item_ids(db_conn, row["id"]) == {1, 2}
    assert repo.get_checkpoint(db_conn, row["id"]) == datetime.datetime(2026, 7, 2)
    assert repo.get_area_path(db_conn, row["id"])["is_running"] is False


def test_delta_deletes_items_no_longer_in_scope(db_conn):
    row = _area_path_row(db_conn)
    repo.upsert_work_items(
        db_conn,
        row["id"],
        [
            {
                "id": 1,
                "title": "A",
                "work_item_type": "Bug",
                "state": "Active",
                "assigned_to": None,
                "changed_date": datetime.datetime(2026, 7, 1),
                "raw_json": "{}",
            },
            {
                "id": 2,
                "title": "B",
                "work_item_type": "Task",
                "state": "New",
                "assigned_to": None,
                "changed_date": datetime.datetime(2026, 7, 2),
                "raw_json": "{}",
            },
        ],
    )
    repo.set_checkpoint(db_conn, row["id"], datetime.datetime(2026, 7, 2))
    db_conn.commit()
    row = repo.get_area_path(db_conn, row["id"])

    client = MagicMock()
    client.get_all_ids.return_value = [2]  # item 1 no longer exists / moved out
    client.get_changed_ids.return_value = []
    client.get_work_items_batch.return_value = []

    result = sync_service.run_sync(db_conn, row, client)
    db_conn.commit()

    assert result["status"] == "ok"
    assert repo.get_work_item_ids(db_conn, row["id"]) == {2}


def test_skips_when_already_running(db_conn):
    row = _area_path_row(db_conn)
    repo.try_acquire_lock(db_conn, row["id"])
    db_conn.commit()
    row = repo.get_area_path(db_conn, row["id"])

    client = MagicMock()
    result = sync_service.run_sync(db_conn, row, client)

    assert result["status"] == "skipped_running"
    client.get_all_ids.assert_not_called()


def test_auth_error_sets_status_and_releases_lock(db_conn):
    row = _area_path_row(db_conn)
    client = MagicMock()
    client.get_all_ids.side_effect = AdoAuthError("bad token")

    result = sync_service.run_sync(db_conn, row, client)
    db_conn.commit()

    assert result["status"] == "auth_error"
    updated = repo.get_area_path(db_conn, row["id"])
    assert updated["last_sync_status"] == "auth_error"
    assert updated["last_error_msg"] == "bad token"
    assert updated["is_running"] is False


def test_retry_exhausted_sets_error_status(db_conn):
    row = _area_path_row(db_conn)
    client = MagicMock()
    client.get_all_ids.side_effect = AdoRetryExhaustedError("gave up")

    result = sync_service.run_sync(db_conn, row, client)
    db_conn.commit()

    assert result["status"] == "error"
    updated = repo.get_area_path(db_conn, row["id"])
    assert updated["last_sync_status"] == "error"
    assert updated["last_error_msg"] == "gave up"
    assert updated["is_running"] is False


def test_db_error_mid_sync_rolls_back_before_recording_failure(db_conn):
    row = _area_path_row(db_conn)
    client = MagicMock()
    client.get_all_ids.return_value = [1]
    client.get_changed_ids.return_value = [1]
    client.get_work_items_batch.return_value = [
        {
            "id": 1,
            "title": "A",
            "work_item_type": "Bug",
            "state": "Active",
            "assigned_to": None,
            "changed_date": None,
            "raw_json": "{}",
        }
    ]

    def _abort_transaction(*args, **kwargs):
        with db_conn.cursor() as cur:
            cur.execute("SELECT 1/0")  # real Postgres error: aborts the current transaction

    with patch.object(repo, "delete_work_items", side_effect=_abort_transaction):
        result = sync_service.run_sync(db_conn, row, client)
        db_conn.commit()

    assert result["status"] == "error"
    updated = repo.get_area_path(db_conn, row["id"])
    assert updated["last_sync_status"] == "error"
    assert "zero" in updated["last_error_msg"]  # Postgres error text, locale-dependent (e.g. "division by zero")
    assert updated["is_running"] is False
