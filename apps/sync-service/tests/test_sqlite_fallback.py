from pathlib import Path

import pytest

from app import db
from app import config
from app import repository as repo
from app import sync_service
from app.capacity import StatusInterval
from unittest.mock import MagicMock
import datetime


def test_connection_uses_sqlite_when_database_url_is_empty(tmp_path, monkeypatch):
    database_path = tmp_path / "fallback.sqlite3"
    monkeypatch.setattr(db, "get_database_url", lambda: "")
    monkeypatch.setattr(db, "get_sqlite_database_path", lambda: str(database_path))

    conn = db.get_connection()
    db.init_schema(conn)
    with conn.cursor() as cur:
        cur.execute("INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s)", ("o", "p", "a"))
        cur.execute("SELECT area_path FROM area_paths")
        assert cur.fetchone()[0] == "a"
    conn.close()
    assert Path(database_path).exists()


def test_completed_sqlite_sync_releases_running_flag(tmp_path):
    conn = db.SQLiteConnection(str(tmp_path / "sync.sqlite3"))
    db.init_schema(conn)
    area_path_id = repo.create_area_path(conn, "o", "p", "a")
    conn.commit()
    row = repo.get_area_path(conn, area_path_id)
    client = MagicMock()
    client.get_all_ids.return_value = []
    client.get_changed_ids.return_value = []
    client.get_work_items_batch.return_value = []

    result = sync_service.run_sync(conn, row, client)

    assert result["status"] == "ok"
    assert repo.get_area_path(conn, area_path_id)["is_running"] == 0
    conn.close()


def test_sqlite_schema_persists_capacity_intervals_and_snapshot(tmp_path):
    conn = db.SQLiteConnection(str(tmp_path / "capacity.sqlite3"))
    db.init_schema(conn)
    area_path_id = repo.create_area_path(conn, "org", "project", "project\\Area")
    interval = StatusInterval(
        work_item_id=1,
        area_path_id=area_path_id,
        revision=1,
        work_item_type="Bug",
        state="New",
        started_at=datetime.datetime(2026, 7, 1, 9, 0),
        ended_at=datetime.datetime(2026, 7, 2, 9, 0),
    )

    repo.replace_work_item_status_intervals(
        conn, work_item_id=1, area_path_id=area_path_id, intervals=[interval]
    )
    repo.upsert_capacity_snapshot(
        conn,
        area_path_id=area_path_id,
        payload={"forecast": {"expected": 1}},
        generated_at=datetime.datetime(2026, 7, 2, 9, 0),
    )
    conn.commit()

    assert repo.load_capacity_intervals(conn, area_path_id=area_path_id) == [
        {
            "work_item_id": 1,
            "area_path_id": area_path_id,
            "revision": 1,
            "work_item_type": "Bug",
            "state": "New",
            "started_at": datetime.datetime(2026, 7, 1, 9, 0),
            "ended_at": datetime.datetime(2026, 7, 2, 9, 0),
        }
    ]
    assert repo.get_capacity_snapshot(conn, area_path_id=area_path_id) == {
        "forecast": {"expected": 1}
    }
    conn.close()


def test_sqlite_schema_persists_replaces_and_deletes_app_setting(tmp_path):
    conn = db.SQLiteConnection(str(tmp_path / "settings.sqlite3"))
    db.init_schema(conn)
    first = datetime.datetime(2026, 8, 18, 10, 0)
    second = datetime.datetime(2026, 8, 18, 11, 0)

    repo.upsert_app_setting(
        conn,
        key="azure_devops_api_key",
        encrypted_value="cipher-one",
        updated_at=first,
    )
    repo.upsert_app_setting(
        conn,
        key="azure_devops_api_key",
        encrypted_value="cipher-two",
        updated_at=second,
    )
    conn.commit()

    assert repo.get_app_setting(conn, "azure_devops_api_key") == {
        "key": "azure_devops_api_key",
        "encrypted_value": "cipher-two",
        "updated_at": second,
    }
    repo.delete_app_setting(conn, "azure_devops_api_key")
    conn.commit()
    assert repo.get_app_setting(conn, "azure_devops_api_key") is None
    conn.close()


def test_sqlite_app_setting_rejects_unknown_key(tmp_path):
    conn = db.SQLiteConnection(str(tmp_path / "settings.sqlite3"))
    db.init_schema(conn)

    with pytest.raises(
        ValueError, match="app setting key must be 'azure_devops_api_key'"
    ):
        repo.upsert_app_setting(
            conn,
            key="unexpected_key",
            encrypted_value="cipher-one",
            updated_at=datetime.datetime(2026, 8, 18, 10, 0),
        )

    conn.close()


def test_sqlite_app_setting_rejects_values_longer_than_4096(tmp_path):
    conn = db.SQLiteConnection(str(tmp_path / "settings.sqlite3"))
    db.init_schema(conn)

    with pytest.raises(
        ValueError, match="app setting encrypted_value must be at most 4096 characters"
    ):
        repo.upsert_app_setting(
            conn,
            key="azure_devops_api_key",
            encrypted_value="x" * 4097,
            updated_at=datetime.datetime(2026, 8, 18, 10, 0),
        )

    conn.close()
