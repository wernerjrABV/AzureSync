import datetime
import sqlite3
from pathlib import Path

import psycopg

from app.config import get_database_url, get_sqlite_database_path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS area_paths (
    id SERIAL PRIMARY KEY,
    organization TEXT NOT NULL,
    project TEXT NOT NULL,
    area_path TEXT NOT NULL,
    incluir_subpaths BOOLEAN NOT NULL DEFAULT TRUE,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    intervalo_minutos INTEGER NOT NULL DEFAULT 60,
    is_running BOOLEAN NOT NULL DEFAULT FALSE,
    last_sync_at TIMESTAMP,
    last_sync_status TEXT,
    last_sync_count INTEGER,
    last_error_msg TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS work_items (
    id INTEGER PRIMARY KEY,
    area_path_id INTEGER NOT NULL REFERENCES area_paths(id),
    title TEXT,
    work_item_type TEXT,
    state TEXT,
    assigned_to TEXT,
    changed_date TIMESTAMP,
    parent_id INTEGER,
    raw_json JSONB,
    synced_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sync_checkpoints (
    area_path_id INTEGER PRIMARY KEY REFERENCES area_paths(id),
    last_changed_date TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_logs (
    id SERIAL PRIMARY KEY,
    area_path_id INTEGER NOT NULL REFERENCES area_paths(id),
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    status TEXT,
    items_processed INTEGER,
    error_msg TEXT
);

CREATE TABLE IF NOT EXISTS work_item_history (
    work_item_id INTEGER NOT NULL,
    area_path_id INTEGER NOT NULL REFERENCES area_paths(id),
    rev INTEGER NOT NULL,
    revised_by TEXT,
    revised_date TIMESTAMP,
    raw_json JSONB,
    synced_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (work_item_id, rev)
);

ALTER TABLE area_paths ADD COLUMN IF NOT EXISTS last_error_msg TEXT;
ALTER TABLE area_paths ADD COLUMN IF NOT EXISTS history_loaded_at TIMESTAMP;
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS parent_id INTEGER;
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS start_date TIMESTAMP;
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS target_date TIMESTAMP;
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS created_date TIMESTAMP;
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS activated_date TIMESTAMP;
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS closed_date TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_work_items_area_path_id ON work_items (area_path_id);
CREATE INDEX IF NOT EXISTS idx_work_items_area_path_changed_date ON work_items (area_path_id, changed_date DESC);
CREATE INDEX IF NOT EXISTS idx_work_items_type ON work_items (work_item_type) WHERE work_item_type IS NOT NULL;
"""


class SQLiteCursor:
    def __init__(self, cursor, row_factory=None):
        self.cursor, self.row_factory = cursor, row_factory
    def __enter__(self): return self
    def __exit__(self, *args): self.cursor.close()
    def execute(self, sql, params=()):
        sql = sql.replace("%s", "?").replace("now()", "CURRENT_TIMESTAMP")
        if ";" in sql and not params:
            self.cursor.executescript(sql)
        else:
            self.cursor.execute(sql, params)
        return self
    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return row
        values = self._convert_row(row)
        return dict(zip(self._columns(), values)) if self.row_factory else values
    def fetchall(self):
        rows = self.cursor.fetchall()
        converted = [self._convert_row(row) for row in rows]
        return [dict(zip(self._columns(), row)) for row in converted] if self.row_factory else converted

    @staticmethod
    def _convert_value(column, value):
        if not isinstance(value, str) or not any(token in column.lower() for token in ("_at", "_date")):
            return value
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return value

    def _convert_row(self, row):
        return tuple(self._convert_value(column, value) for column, value in zip(self._columns(), row))

    def _columns(self):
        return [description[0] for description in self.cursor.description]


class SQLiteConnection:
    is_sqlite = True
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=30000")
    def cursor(self, row_factory=None): return SQLiteCursor(self.connection.cursor(), row_factory)
    def commit(self): self.connection.commit()
    def rollback(self): self.connection.rollback()
    def close(self): self.connection.close()


def get_connection():
    if get_database_url():
        try:
            return psycopg.connect(get_database_url())
        except psycopg.Error:
            pass
    return SQLiteConnection(get_sqlite_database_path())


def init_schema(conn: psycopg.Connection) -> None:
    if getattr(conn, "is_sqlite", False):
        with conn.cursor() as cur:
            cur.execute(SQLITE_SCHEMA_SQL)
        return
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)


SQLITE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS area_paths (id INTEGER PRIMARY KEY AUTOINCREMENT, organization TEXT NOT NULL, project TEXT NOT NULL, area_path TEXT NOT NULL, incluir_subpaths INTEGER NOT NULL DEFAULT 1, ativo INTEGER NOT NULL DEFAULT 1, intervalo_minutos INTEGER NOT NULL DEFAULT 60, is_running INTEGER NOT NULL DEFAULT 0, last_sync_at TIMESTAMP, last_sync_status TEXT, last_sync_count INTEGER, last_error_msg TEXT, history_loaded_at TIMESTAMP, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS work_items (id INTEGER PRIMARY KEY, area_path_id INTEGER NOT NULL, title TEXT, work_item_type TEXT, state TEXT, assigned_to TEXT, changed_date TIMESTAMP, parent_id INTEGER, raw_json TEXT, synced_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, start_date TIMESTAMP, target_date TIMESTAMP, created_date TIMESTAMP, activated_date TIMESTAMP, closed_date TIMESTAMP);
CREATE TABLE IF NOT EXISTS sync_checkpoints (area_path_id INTEGER PRIMARY KEY, last_changed_date TIMESTAMP);
CREATE TABLE IF NOT EXISTS sync_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, area_path_id INTEGER NOT NULL, started_at TIMESTAMP NOT NULL, finished_at TIMESTAMP, status TEXT, items_processed INTEGER, error_msg TEXT);
CREATE TABLE IF NOT EXISTS work_item_history (work_item_id INTEGER NOT NULL, area_path_id INTEGER NOT NULL, rev INTEGER NOT NULL, revised_by TEXT, revised_date TIMESTAMP, raw_json TEXT, synced_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (work_item_id, rev));
"""
