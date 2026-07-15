from app import repository as repo


def _seed_area_path(conn, organization="org", project="proj", area_path="proj\\A"):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s) RETURNING id",
            (organization, project, area_path),
        )
        area_path_id = cur.fetchone()[0]
    conn.commit()
    return area_path_id


def _seed_work_item(conn, area_path_id, item_id, title, work_item_type, changed_date):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO work_items (id, area_path_id, title, work_item_type, state, changed_date, raw_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (item_id, area_path_id, title, work_item_type, "Active", changed_date, "{}"),
        )
    conn.commit()


def test_list_area_paths_returns_all(db_conn):
    _seed_area_path(db_conn, area_path="proj\\A")
    _seed_area_path(db_conn, area_path="proj\\B")

    rows = repo.list_area_paths(db_conn)

    assert [r["area_path"] for r in rows] == ["proj\\A", "proj\\B"]


def test_list_work_items_filters_by_area_path_id(db_conn):
    ap1 = _seed_area_path(db_conn, area_path="proj\\A")
    ap2 = _seed_area_path(db_conn, area_path="proj\\B")
    _seed_work_item(db_conn, ap1, 1, "Item 1", "Bug", "2026-01-01T00:00:00")
    _seed_work_item(db_conn, ap2, 2, "Item 2", "Bug", "2026-01-02T00:00:00")

    rows, total = repo.list_work_items(db_conn, area_path_id=ap1)

    assert total == 1
    assert [r["id"] for r in rows] == [1]


def test_list_work_items_paginates(db_conn):
    ap1 = _seed_area_path(db_conn)
    for i in range(1, 6):
        _seed_work_item(db_conn, ap1, i, f"Item {i}", "Task", f"2026-01-0{i}T00:00:00")

    rows, total = repo.list_work_items(db_conn, page=1, page_size=2, order_by="id", order_dir="asc")

    assert total == 5
    assert [r["id"] for r in rows] == [1, 2]


def test_list_work_items_orders_desc_by_default(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_work_item(db_conn, ap1, 1, "Older", "Task", "2026-01-01T00:00:00")
    _seed_work_item(db_conn, ap1, 2, "Newer", "Task", "2026-01-02T00:00:00")

    rows, _ = repo.list_work_items(db_conn)

    assert [r["id"] for r in rows] == [2, 1]
