from pathlib import Path

from app import db
from app import config
from app import repository as repo
from app import sync_service
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
