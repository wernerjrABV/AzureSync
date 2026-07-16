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

    rows, total = repo.list_work_items(db_conn, area_path_id=ap1, page=1, page_size=2, order_by="id", order_dir="asc")

    assert total == 5
    assert [r["id"] for r in rows] == [1, 2]


def test_list_work_items_orders_desc_by_default(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_work_item(db_conn, ap1, 1, "Older", "Task", "2026-01-01T00:00:00")
    _seed_work_item(db_conn, ap1, 2, "Newer", "Task", "2026-01-02T00:00:00")

    rows, _ = repo.list_work_items(db_conn, area_path_id=ap1)

    assert [r["id"] for r in rows] == [2, 1]


def test_list_work_items_requires_area_path_id(db_conn):
    import pytest
    from app.repository import InvalidQueryParam

    with pytest.raises(InvalidQueryParam):
        repo.list_work_items(db_conn, area_path_id=None)


def test_list_work_items_search_matches_title(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_work_item(db_conn, ap1, 1, "Fix login bug", "Bug", "2026-01-01T00:00:00")
    _seed_work_item(db_conn, ap1, 2, "Add export button", "Task", "2026-01-02T00:00:00")

    rows, total = repo.list_work_items(db_conn, area_path_id=ap1, search="login")

    assert total == 1
    assert rows[0]["id"] == 1


def test_list_work_items_search_matches_id(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_work_item(db_conn, ap1, 42, "Item A", "Bug", "2026-01-01T00:00:00")
    _seed_work_item(db_conn, ap1, 43, "Item B", "Bug", "2026-01-02T00:00:00")

    rows, total = repo.list_work_items(db_conn, area_path_id=ap1, search="42")

    assert total == 1
    assert rows[0]["id"] == 42


def test_list_work_items_search_matches_work_item_type(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_work_item(db_conn, ap1, 1, "Item A", "Bug", "2026-01-01T00:00:00")
    _seed_work_item(db_conn, ap1, 2, "Item B", "Task", "2026-01-02T00:00:00")

    rows, total = repo.list_work_items(db_conn, area_path_id=ap1, search="task")

    assert total == 1
    assert rows[0]["id"] == 2


def test_list_work_items_search_matches_state(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_work_item(db_conn, ap1, 1, "Item A", "Bug", "2026-01-01T00:00:00")
    with db_conn.cursor() as cur:
        cur.execute("UPDATE work_items SET state = 'Resolved' WHERE id = 1")
    db_conn.commit()

    rows, total = repo.list_work_items(db_conn, area_path_id=ap1, search="resolved")

    assert total == 1
    assert rows[0]["id"] == 1


def test_list_work_items_search_matches_assigned_to(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_work_item(db_conn, ap1, 1, "Item A", "Bug", "2026-01-01T00:00:00")
    with db_conn.cursor() as cur:
        cur.execute("UPDATE work_items SET assigned_to = 'Alice' WHERE id = 1")
    db_conn.commit()

    rows, total = repo.list_work_items(db_conn, area_path_id=ap1, search="alice")

    assert total == 1
    assert rows[0]["id"] == 1


def test_list_work_items_search_combines_with_area_path_filter(db_conn):
    ap1 = _seed_area_path(db_conn, area_path="proj\\A")
    ap2 = _seed_area_path(db_conn, area_path="proj\\B")
    _seed_work_item(db_conn, ap1, 1, "Shared title", "Bug", "2026-01-01T00:00:00")
    _seed_work_item(db_conn, ap2, 2, "Shared title", "Bug", "2026-01-01T00:00:00")

    rows, total = repo.list_work_items(db_conn, area_path_id=ap1, search="Shared")

    assert total == 1
    assert rows[0]["id"] == 1


def test_list_work_items_empty_search_returns_all(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_work_item(db_conn, ap1, 1, "Item A", "Bug", "2026-01-01T00:00:00")

    rows, total = repo.list_work_items(db_conn, area_path_id=ap1, search="")

    assert total == 1
