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
