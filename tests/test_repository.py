from app import repository as repo


def test_create_and_get_area_path(db_conn):
    area_path_id = repo.create_area_path(
        db_conn, "myorg", "myproj", "myproj\\Team A", incluir_subpaths=False, intervalo_minutos=30
    )
    db_conn.commit()

    row = repo.get_area_path(db_conn, area_path_id)

    assert row["organization"] == "myorg"
    assert row["project"] == "myproj"
    assert row["area_path"] == "myproj\\Team A"
    assert row["incluir_subpaths"] is False
    assert row["ativo"] is True
    assert row["intervalo_minutos"] == 30
    assert row["is_running"] is False


def test_list_area_paths_returns_all(db_conn):
    repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    repo.create_area_path(db_conn, "org", "proj", "proj\\B")
    db_conn.commit()

    rows = repo.list_area_paths(db_conn)

    assert len(rows) == 2


def test_update_area_path(db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()

    repo.update_area_path(db_conn, area_path_id, ativo=False, intervalo_minutos=15)
    db_conn.commit()

    row = repo.get_area_path(db_conn, area_path_id)
    assert row["ativo"] is False
    assert row["intervalo_minutos"] == 15


def test_delete_area_path(db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()

    repo.delete_area_path(db_conn, area_path_id)
    db_conn.commit()

    assert repo.get_area_path(db_conn, area_path_id) is None


def test_acquire_lock_succeeds_when_free(db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()

    acquired = repo.try_acquire_lock(db_conn, area_path_id)
    db_conn.commit()

    assert acquired is True
    assert repo.get_area_path(db_conn, area_path_id)["is_running"] is True


def test_acquire_lock_fails_when_already_running(db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()
    repo.try_acquire_lock(db_conn, area_path_id)
    db_conn.commit()

    acquired_again = repo.try_acquire_lock(db_conn, area_path_id)
    db_conn.commit()

    assert acquired_again is False


def test_release_lock(db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()
    repo.try_acquire_lock(db_conn, area_path_id)
    db_conn.commit()

    repo.release_lock(db_conn, area_path_id)
    db_conn.commit()

    assert repo.get_area_path(db_conn, area_path_id)["is_running"] is False


def test_update_sync_result(db_conn):
    import datetime

    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()

    now = datetime.datetime(2026, 7, 15, 10, 0, 0)
    repo.update_sync_result(db_conn, area_path_id, status="ok", count=42, synced_at=now)
    db_conn.commit()

    row = repo.get_area_path(db_conn, area_path_id)
    assert row["last_sync_status"] == "ok"
    assert row["last_sync_count"] == 42
    assert row["last_sync_at"] == now


import datetime
import json


def _make_area_path(db_conn):
    area_path_id = repo.create_area_path(db_conn, "org", "proj", "proj\\A")
    db_conn.commit()
    return area_path_id


def test_checkpoint_roundtrip(db_conn):
    area_path_id = _make_area_path(db_conn)
    assert repo.get_checkpoint(db_conn, area_path_id) is None

    when = datetime.datetime(2026, 7, 15, 9, 30, 0)
    repo.set_checkpoint(db_conn, area_path_id, when)
    db_conn.commit()

    assert repo.get_checkpoint(db_conn, area_path_id) == when

    later = datetime.datetime(2026, 7, 16, 9, 30, 0)
    repo.set_checkpoint(db_conn, area_path_id, later)
    db_conn.commit()

    assert repo.get_checkpoint(db_conn, area_path_id) == later


def test_upsert_and_get_work_item_ids(db_conn):
    area_path_id = _make_area_path(db_conn)
    items = [
        {
            "id": 1,
            "title": "Bug A",
            "work_item_type": "Bug",
            "state": "Active",
            "assigned_to": "alice@example.com",
            "changed_date": datetime.datetime(2026, 7, 1),
            "raw_json": json.dumps({"id": 1}),
        },
        {
            "id": 2,
            "title": "Task B",
            "work_item_type": "Task",
            "state": "New",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 2),
            "raw_json": json.dumps({"id": 2}),
        },
    ]

    repo.upsert_work_items(db_conn, area_path_id, items)
    db_conn.commit()

    assert repo.get_work_item_ids(db_conn, area_path_id) == {1, 2}

    items[0]["title"] = "Bug A (renamed)"
    repo.upsert_work_items(db_conn, area_path_id, [items[0]])
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT title FROM work_items WHERE id = 1")
        assert cur.fetchone()[0] == "Bug A (renamed)"


def test_delete_work_items(db_conn):
    area_path_id = _make_area_path(db_conn)
    items = [
        {
            "id": 1,
            "title": "Bug A",
            "work_item_type": "Bug",
            "state": "Active",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 1),
            "raw_json": json.dumps({"id": 1}),
        },
        {
            "id": 2,
            "title": "Task B",
            "work_item_type": "Task",
            "state": "New",
            "assigned_to": None,
            "changed_date": datetime.datetime(2026, 7, 2),
            "raw_json": json.dumps({"id": 2}),
        },
    ]
    repo.upsert_work_items(db_conn, area_path_id, items)
    db_conn.commit()

    repo.delete_work_items(db_conn, area_path_id, {1})
    db_conn.commit()

    assert repo.get_work_item_ids(db_conn, area_path_id) == {2}


def test_sync_log_lifecycle(db_conn):
    area_path_id = _make_area_path(db_conn)
    started = datetime.datetime(2026, 7, 15, 10, 0, 0)

    log_id = repo.create_sync_log(db_conn, area_path_id, started)
    db_conn.commit()

    finished = datetime.datetime(2026, 7, 15, 10, 5, 0)
    repo.finish_sync_log(db_conn, log_id, finished, status="ok", items_processed=10)
    db_conn.commit()

    with db_conn.cursor(row_factory=repo.dict_row) as cur:
        cur.execute("SELECT * FROM sync_logs WHERE id = %s", (log_id,))
        row = cur.fetchone()

    assert row["status"] == "ok"
    assert row["items_processed"] == 10
    assert row["finished_at"] == finished
    assert row["error_msg"] is None
