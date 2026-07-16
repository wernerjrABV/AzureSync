import psycopg

from app.config import get_database_url

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

CREATE INDEX IF NOT EXISTS idx_work_items_area_path_id ON work_items (area_path_id);
CREATE INDEX IF NOT EXISTS idx_work_items_area_path_changed_date ON work_items (area_path_id, changed_date DESC);
CREATE INDEX IF NOT EXISTS idx_work_items_type ON work_items (work_item_type) WHERE work_item_type IS NOT NULL;
"""


def get_connection() -> psycopg.Connection:
    return psycopg.connect(get_database_url())


def init_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
