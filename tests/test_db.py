from app import db


def test_init_schema_creates_all_tables(db_conn):
    db.init_schema(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            """
        )
        tables = {row[0] for row in cur.fetchall()}

    assert {"area_paths", "work_items", "sync_checkpoints", "sync_logs"} <= tables
