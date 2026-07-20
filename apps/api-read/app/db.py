import sqlite3
from pathlib import Path

import psycopg

from app.config import get_database_url, get_sqlite_database_path


class SQLiteCursor:
    def __init__(self, cursor, row_factory=None): self.cursor, self.row_factory = cursor, row_factory
    def __enter__(self): return self
    def __exit__(self, *args): self.cursor.close()
    def execute(self, sql, params=()):
        self.cursor.execute(sql.replace("%s", "?").replace("ILIKE", "LIKE").replace("id::text", "CAST(id AS TEXT)"), params); return self
    def fetchone(self):
        row = self.cursor.fetchone(); return dict(row) if row is not None and self.row_factory else row
    def fetchall(self):
        rows = self.cursor.fetchall(); return [dict(row) for row in rows] if self.row_factory else rows


class SQLiteConnection:
    is_sqlite = True
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=30); self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=30000")
    def cursor(self, row_factory=None): return SQLiteCursor(self.connection.cursor(), row_factory)
    def commit(self): self.connection.commit()
    def rollback(self): self.connection.rollback()
    def close(self): self.connection.close()
    def init_schema(self):
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS area_paths (id INTEGER PRIMARY KEY, organization TEXT, project TEXT, area_path TEXT);
        CREATE TABLE IF NOT EXISTS work_items (id INTEGER PRIMARY KEY, area_path_id INTEGER, title TEXT, work_item_type TEXT, state TEXT, assigned_to TEXT, changed_date TEXT, parent_id INTEGER, raw_json TEXT, synced_at TEXT, start_date TEXT, target_date TEXT, created_date TEXT, activated_date TEXT, closed_date TEXT);
        CREATE TABLE IF NOT EXISTS work_item_history (work_item_id INTEGER, area_path_id INTEGER, rev INTEGER, revised_by TEXT, revised_date TEXT, raw_json TEXT, synced_at TEXT, PRIMARY KEY(work_item_id, rev));
        """)


def get_connection():
    if get_database_url():
        try: return psycopg.connect(get_database_url())
        except psycopg.Error: pass
    conn = SQLiteConnection(get_sqlite_database_path()); conn.init_schema(); return conn
