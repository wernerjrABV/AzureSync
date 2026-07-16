import os

import psycopg
import pytest


@pytest.fixture
def db_conn():
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL not set")

    conn = psycopg.connect(dsn)

    with conn.cursor() as cur:
        cur.execute(
            "TRUNCATE sync_logs, sync_checkpoints, work_item_history, work_items, area_paths RESTART IDENTITY CASCADE"
        )
    conn.commit()

    yield conn

    conn.rollback()
    conn.close()
