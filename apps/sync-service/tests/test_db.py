from app import db


def test_init_schema_creates_work_item_history_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'work_item_history'
            ORDER BY column_name
            """
        )
        columns = {row[0]: row[1] for row in cur.fetchall()}

    assert columns["work_item_id"] == "integer"
    assert columns["area_path_id"] == "integer"
    assert columns["rev"] == "integer"
    assert columns["revised_by"] == "text"
    assert columns["revised_date"] == "timestamp without time zone"
    assert columns["raw_json"] == "jsonb"
    assert columns["synced_at"] == "timestamp without time zone"


def test_init_schema_adds_history_loaded_at_column(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'area_paths' AND column_name = 'history_loaded_at'
            """
        )
        row = cur.fetchone()

    assert row is not None
    assert row[0] == "timestamp without time zone"
