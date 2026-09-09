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


def test_cancellation_stops_before_remote_work_and_releases_lock(db_conn):
    row = _area_path_row(db_conn)
    client = MagicMock()

    result = sync_service.run_sync(db_conn, row, client, should_cancel=lambda: True)
    db_conn.commit()

    assert result["status"] == "cancelled"
    client.get_all_ids.assert_not_called()
    updated = repo.get_area_path(db_conn, row["id"])
    assert updated["last_sync_status"] == "cancelled"
    assert updated["is_running"] is False


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


def test_missing_stored_credential_sets_auth_error_status(db_conn):
    row = _area_path_row(db_conn)
    client = AdoClient("org", "proj", pat_provider=lambda: None)

    result = sync_service.run_sync(db_conn, row, client)
    db_conn.commit()

    assert result["status"] == "auth_error"
    updated = repo.get_area_path(db_conn, row["id"])
    assert updated["last_sync_status"] == "auth_error"
    assert updated["last_error_msg"] == "Azure DevOps credential is not configured"
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


def test_first_sync_with_missing_current_type_leaves_history_marker_unset(db_conn):
    row = _area_path_row(db_conn)
    client = MagicMock()
    client.get_all_ids.return_value = [1, 2]
    client.get_changed_ids.return_value = [1]  # only item 1 changed
    client.get_work_items_batch.return_value = [
        {
            "id": 1,
            "title": "A",
            "work_item_type": "Bug",
            "state": "Active",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 1),
            "raw_json": "{}",
        }
    ]
    client.get_work_item_updates.return_value = [
        {"rev": 1, "revisedBy": {"uniqueName": "alice@example.com"}, "revisedDate": "2026-07-01T10:00:00Z", "fields": {}}
    ]

    result = sync_service.run_sync(db_conn, row, client)
    db_conn.commit()

    assert result["status"] == "ok"
    # first sync: history fetched for every current id (1 and 2), not just the changed one
    called_ids = sorted(call.args[0] for call in client.get_work_item_updates.call_args_list)
    assert called_ids == [1, 2]
    assert repo.get_history_loaded_at(db_conn, row["id"]) is None
    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM work_item_history WHERE work_item_id IN (1, 2)")
        assert cur.fetchone()[0] == 2


def test_subsequent_sync_only_fetches_history_for_delta(db_conn):
    row = _area_path_row(db_conn)
    repo.set_history_loaded(db_conn, row["id"], datetime.datetime(2026, 7, 10))
    db_conn.commit()
    row = repo.get_area_path(db_conn, row["id"])

    client = MagicMock()
    client.get_all_ids.return_value = [1, 2]
    client.get_changed_ids.return_value = [2]  # only item 2 changed this cycle
    client.get_work_items_batch.return_value = [
        {
            "id": 2,
            "title": "B",
            "work_item_type": "Task",
            "state": "New",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 15),
            "raw_json": "{}",
        }
    ]
    client.get_work_item_updates.return_value = []

    result = sync_service.run_sync(db_conn, row, client)
    db_conn.commit()

    assert result["status"] == "ok"
    called_ids = [call.args[0] for call in client.get_work_item_updates.call_args_list]
    assert called_ids == [2]


def test_history_sync_failure_leaves_history_loaded_at_unset(db_conn):
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
            "changed_date": datetime.datetime(2026, 7, 1),
            "raw_json": "{}",
        }
    ]
    client.get_work_item_updates.side_effect = AdoRetryExhaustedError("gave up")

    result = sync_service.run_sync(db_conn, row, client)
    db_conn.commit()

    # a poison history item must not fail the whole sync (Finding 1)
    assert result["status"] == "ok"
    assert repo.get_history_loaded_at(db_conn, row["id"]) is None
    updated = repo.get_area_path(db_conn, row["id"])
    assert updated["last_sync_status"] == "ok"
    assert updated["is_running"] is False


def test_poison_history_item_does_not_block_other_items_or_checkpoint(db_conn):
    row = _area_path_row(db_conn)
    client = MagicMock()
    client.get_all_ids.return_value = [1, 2, 3]
    client.get_changed_ids.return_value = [1, 2, 3]
    client.get_work_items_batch.return_value = [
        {
            "id": wid,
            "title": f"Item {wid}",
            "work_item_type": "Bug",
            "state": "Active",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, wid),
            "raw_json": "{}",
        }
        for wid in (1, 2, 3)
    ]

    def _updates_side_effect(work_item_id):
        if work_item_id == 2:
            raise AdoRetryExhaustedError("permanently broken item")
        return [
            {
                "rev": 1,
                "revisedBy": {"uniqueName": "alice@example.com"},
                "revisedDate": "2026-07-01T10:00:00Z",
                "fields": {},
            }
        ]

    client.get_work_item_updates.side_effect = _updates_side_effect

    result = sync_service.run_sync(db_conn, row, client)
    db_conn.commit()

    # sync overall must still succeed: work item upserts/deletes/checkpoint aren't rolled back
    assert result["status"] == "ok"
    assert repo.get_work_item_ids(db_conn, row["id"]) == {1, 2, 3}
    assert repo.get_checkpoint(db_conn, row["id"]) == datetime.datetime(2026, 7, 3)

    # the poisoned item (2) has no history rows, but the healthy items (1, 3) do
    with db_conn.cursor() as cur:
        cur.execute("SELECT work_item_id FROM work_item_history ORDER BY work_item_id")
        assert [r[0] for r in cur.fetchall()] == [1, 3]

    # this was a first-load backfill and not every item succeeded, so history_loaded_at must stay unset
    assert repo.get_history_loaded_at(db_conn, row["id"]) is None


def test_successful_history_sync_publishes_capacity_snapshot(db_conn):
    row = _area_path_row(db_conn)
    client = MagicMock()
    client.get_all_ids.return_value = [1]
    client.get_changed_ids.return_value = [1]
    client.get_work_items_batch.return_value = [
        {
            "id": 1,
            "title": "A",
            "work_item_type": "Bug",
            "state": "Closed",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 1),
            "raw_json": "{}",
        }
    ]
    client.get_work_item_updates.return_value = [
        {
            "rev": 1,
            "revisedDate": "2026-06-01T09:00:00Z",
            "fields": {"System.State": {"newValue": "New"}},
        },
        {
            "rev": 2,
            "revisedDate": "2026-07-01T09:00:00Z",
            "fields": {"System.State": {"newValue": "Closed"}},
        },
    ]

    result = sync_service.run_sync(db_conn, row, client)

    assert result["status"] == "ok"
    snapshot = repo.get_capacity_snapshot(db_conn, area_path_id=row["id"])
    assert snapshot is not None
    assert snapshot["generated_at"]
    assert snapshot["monthly_throughput"][-1] == {"month": "2026-07", "count": 1}


def test_poisoned_history_retains_previous_capacity_snapshot(db_conn):
    row = _area_path_row(db_conn)
    previous = {"generated_at": "2026-07-01T09:00:00", "forecast": {"expected": 5}}
    repo.upsert_capacity_snapshot(
        db_conn,
        area_path_id=row["id"],
        payload=previous,
        generated_at=datetime.datetime(2026, 7, 1, 9, 0),
    )
    db_conn.commit()

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
            "changed_date": datetime.datetime(2026, 7, 2),
            "raw_json": "{}",
        }
    ]
    client.get_work_item_updates.side_effect = AdoRetryExhaustedError("poisoned")

    result = sync_service.run_sync(db_conn, row, client)

    assert result["status"] == "ok"
    assert repo.get_capacity_snapshot(db_conn, area_path_id=row["id"]) == previous


def test_missing_current_work_item_type_retains_previous_capacity_snapshot(db_conn):
    row = _area_path_row(db_conn)
    previous = {"generated_at": "2026-07-01T09:00:00", "forecast": {"expected": 5}}
    repo.upsert_capacity_snapshot(
        db_conn,
        area_path_id=row["id"],
        payload=previous,
        generated_at=datetime.datetime(2026, 7, 1, 9, 0),
    )
    db_conn.commit()

    client = MagicMock()
    client.get_all_ids.return_value = [1]
    client.get_changed_ids.return_value = [1]
    client.get_work_items_batch.return_value = []
    client.get_work_item_updates.return_value = [
        {
            "rev": 1,
            "revisedDate": "2026-07-02T09:00:00Z",
            "fields": {"System.State": {"newValue": "New"}},
        }
    ]

    result = sync_service.run_sync(db_conn, row, client)

    assert result["status"] == "ok"
    assert repo.get_capacity_snapshot(db_conn, area_path_id=row["id"]) == previous
    assert repo.get_history_loaded_at(db_conn, row["id"]) is None


def test_second_sync_rebuilds_capacity_from_all_stored_history_revisions(db_conn):
    row = _area_path_row(db_conn)
    first_client = MagicMock()
    first_client.get_all_ids.return_value = [1]
    first_client.get_changed_ids.return_value = [1]
    first_client.get_work_items_batch.return_value = [
        {
            "id": 1,
            "title": "A",
            "work_item_type": "Bug",
            "state": "Development",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 6, 2),
            "raw_json": "{}",
        }
    ]
    first_client.get_work_item_updates.return_value = [
        {
            "rev": 1,
            "revisedDate": "2026-06-01T09:00:00Z",
            "fields": {"System.State": {"newValue": "New"}},
        },
        {
            "rev": 2,
            "revisedDate": "2026-06-02T09:00:00Z",
            "fields": {"System.State": {"newValue": "Development"}},
        },
    ]
    assert sync_service.run_sync(db_conn, row, first_client)["status"] == "ok"

    second_client = MagicMock()
    second_client.get_all_ids.return_value = [1]
    second_client.get_changed_ids.return_value = [1]
    second_client.get_work_items_batch.return_value = [
        {
            "id": 1,
            "title": "A",
            "work_item_type": "Bug",
            "state": "Closed",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 1),
            "raw_json": "{}",
        }
    ]
    second_client.get_work_item_updates.return_value = [
        {
            "rev": 3,
            "revisedDate": "2026-07-01T09:00:00Z",
            "fields": {"System.State": {"newValue": "Closed"}},
        }
    ]

    assert sync_service.run_sync(db_conn, row, second_client)["status"] == "ok"

    intervals = repo.load_capacity_intervals(db_conn, area_path_id=row["id"])
    assert [interval["revision"] for interval in intervals] == [1, 2, 3]
    snapshot = repo.get_capacity_snapshot(db_conn, area_path_id=row["id"])
    assert snapshot is not None
    assert snapshot["monthly_throughput"][-1] == {"month": "2026-07", "count": 1}
