import datetime
import json

from app import repository as repo
from app.db import SQLiteConnection


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


def _seed_capacity_snapshot(conn, area_path_id, generated_at, payload):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO capacity_snapshots (area_path_id, generated_at, payload)
            VALUES (%s, %s, %s)
            """,
            (area_path_id, generated_at, json.dumps(payload)),
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


def _seed_feature_tree_item(
    conn, area_path_id, item_id, title, work_item_type, parent_id=None,
    start_date=None, target_date=None, state="Active",
    created_date=None, activated_date=None, closed_date=None,
):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO work_items
                (id, area_path_id, title, work_item_type, state, parent_id,
                 start_date, target_date, created_date, activated_date, closed_date, raw_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '{}')
            """,
            (
                item_id, area_path_id, title, work_item_type, state, parent_id,
                start_date, target_date, created_date, activated_date, closed_date,
            ),
        )
    conn.commit()


def test_list_features_tree_returns_only_feature_epic_solution(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_feature_tree_item(db_conn, ap1, 1, "Sol A", "Solution")
    _seed_feature_tree_item(db_conn, ap1, 2, "Epic A", "Epic", parent_id=1)
    _seed_feature_tree_item(db_conn, ap1, 3, "Feat A", "Feature", parent_id=2)
    _seed_feature_tree_item(db_conn, ap1, 4, "Bug A", "Bug", parent_id=2)

    rows = repo.list_features_tree(db_conn, area_path_id=ap1)

    assert [r["id"] for r in rows] == [1, 2, 3]


def test_list_features_tree_filters_by_area_path_id(db_conn):
    ap1 = _seed_area_path(db_conn, area_path="proj\\A")
    ap2 = _seed_area_path(db_conn, area_path="proj\\B")
    _seed_feature_tree_item(db_conn, ap1, 1, "Feat A", "Feature")
    _seed_feature_tree_item(db_conn, ap2, 2, "Feat B", "Feature")

    rows = repo.list_features_tree(db_conn, area_path_id=ap1)

    assert [r["id"] for r in rows] == [1]


def test_list_features_tree_includes_dates_and_parent(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_feature_tree_item(
        db_conn, ap1, 1, "Feat A", "Feature", parent_id=None,
        start_date="2026-01-10T00:00:00", target_date="2026-02-28T00:00:00",
    )

    rows = repo.list_features_tree(db_conn, area_path_id=ap1)

    assert rows[0]["parent_id"] is None
    assert rows[0]["start_date"].isoformat() == "2026-01-10T00:00:00"
    assert rows[0]["target_date"].isoformat() == "2026-02-28T00:00:00"


def test_list_features_tree_includes_created_activated_closed_dates(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_feature_tree_item(
        db_conn, ap1, 1, "Feat A", "Feature", state="Closed",
        created_date="2025-11-01T09:00:00",
        activated_date="2025-12-01T09:00:00",
        closed_date="2026-06-15T17:30:00",
    )

    rows = repo.list_features_tree(db_conn, area_path_id=ap1)

    assert rows[0]["created_date"].isoformat() == "2025-11-01T09:00:00"
    assert rows[0]["activated_date"].isoformat() == "2025-12-01T09:00:00"
    assert rows[0]["closed_date"].isoformat() == "2026-06-15T17:30:00"
    assert rows[0]["state"] == "Closed"


def test_list_features_tree_excludes_cancelled_and_removed(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_feature_tree_item(db_conn, ap1, 1, "Sol A", "Solution", state="Active")
    _seed_feature_tree_item(db_conn, ap1, 2, "Sol B", "Solution", state="Cancelled")
    _seed_feature_tree_item(db_conn, ap1, 3, "Sol C", "Solution", state="Canceled")
    _seed_feature_tree_item(db_conn, ap1, 4, "Sol D", "Solution", state="Removed")
    _seed_feature_tree_item(db_conn, ap1, 5, "Feat A", "Feature", parent_id=1, state="Active")
    _seed_feature_tree_item(db_conn, ap1, 6, "Feat B", "Feature", parent_id=1, state="Removed")

    rows = repo.list_features_tree(db_conn, area_path_id=ap1)

    assert [r["id"] for r in rows] == [1, 5]


def test_list_features_tree_excludes_closed_solution_with_no_features(db_conn):
    ap1 = _seed_area_path(db_conn)
    # Closed, no children at all -> excluded
    _seed_feature_tree_item(db_conn, ap1, 1, "Sol Empty", "Solution", state="Closed")
    # Closed, has a direct Feature -> kept
    _seed_feature_tree_item(db_conn, ap1, 2, "Sol WithFeature", "Solution", state="Closed")
    _seed_feature_tree_item(db_conn, ap1, 3, "Feat A", "Feature", parent_id=2, state="Active")
    # Closed, has an Epic but that Epic has no Feature -> both Solution and
    # Epic excluded, each by the same closed-with-no-feature rule.
    _seed_feature_tree_item(db_conn, ap1, 4, "Sol WithEmptyEpic", "Solution", state="Closed")
    _seed_feature_tree_item(db_conn, ap1, 5, "Epic Empty", "Epic", parent_id=4, state="Closed")
    # Closed, has an Epic that has a Feature -> kept
    _seed_feature_tree_item(db_conn, ap1, 6, "Sol WithEpicFeature", "Solution", state="Closed")
    _seed_feature_tree_item(db_conn, ap1, 7, "Epic A", "Epic", parent_id=6, state="Active")
    _seed_feature_tree_item(db_conn, ap1, 8, "Feat B", "Feature", parent_id=7, state="Active")
    # Not Closed, no features -> kept (rule only applies to Closed items)
    _seed_feature_tree_item(db_conn, ap1, 9, "Sol Active Empty", "Solution", state="Active")
    # Closed, only has a Removed feature -> treated as no features, excluded
    _seed_feature_tree_item(db_conn, ap1, 10, "Sol OnlyRemovedFeature", "Solution", state="Closed")
    _seed_feature_tree_item(db_conn, ap1, 11, "Feat Removed", "Feature", parent_id=10, state="Removed")

    rows = repo.list_features_tree(db_conn, area_path_id=ap1)

    assert [r["id"] for r in rows] == [2, 3, 6, 7, 8, 9]


def test_list_features_tree_applies_same_closed_no_feature_rule_to_epics(db_conn):
    ap1 = _seed_area_path(db_conn)
    _seed_feature_tree_item(db_conn, ap1, 1, "Sol A", "Solution", state="Active")
    # Closed Epic under an Active Solution, no Feature -> excluded on its own,
    # independent of its parent's state (the two types are treated the same).
    _seed_feature_tree_item(db_conn, ap1, 2, "Epic Empty Closed", "Epic", parent_id=1, state="Closed")
    # Closed Epic under the same Solution, has a Feature -> kept
    _seed_feature_tree_item(db_conn, ap1, 3, "Epic Closed WithFeature", "Epic", parent_id=1, state="Closed")
    _seed_feature_tree_item(db_conn, ap1, 4, "Feat A", "Feature", parent_id=3, state="Active")
    # Active Epic, no Feature -> kept (rule only applies when Closed)
    _seed_feature_tree_item(db_conn, ap1, 5, "Epic Active Empty", "Epic", parent_id=1, state="Active")

    rows = repo.list_features_tree(db_conn, area_path_id=ap1)

    assert [r["id"] for r in rows] == [1, 3, 4, 5]


def test_get_work_item_details(db_conn):
    area_path_id = _seed_area_path(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO work_items
                (id, area_path_id, title, work_item_type, state, assigned_to,
                 changed_date, parent_id, raw_json, synced_at, start_date,
                 target_date, created_date, activated_date, closed_date)
            VALUES
                (42, %s, 'Current title', 'Bug', 'Active', 'Alice',
                 '2026-07-10T12:00:00', 7,
                 '{"fields": {"System.State": "Active"}}',
                 '2026-07-10T12:01:00', '2026-07-01T00:00:00',
                 '2026-08-01T00:00:00', '2026-06-01T00:00:00',
                 '2026-06-02T00:00:00', NULL)
            """,
            (area_path_id,),
        )
        cur.execute(
            """
            INSERT INTO work_item_history
                (work_item_id, area_path_id, rev, revised_by, revised_date, raw_json, synced_at)
            VALUES
                (42, %s, 2, 'bob@example.com', '2026-07-02T10:00:00',
                 '{"rev": 2}', '2026-07-02T10:01:00'),
                (42, %s, 1, 'alice@example.com', '2026-07-01T10:00:00',
                 '{"rev": 1}', '2026-07-01T10:01:00')
            """,
            (area_path_id, area_path_id),
        )
    db_conn.commit()

    details = repo.get_work_item_details(db_conn, work_item_id=42)

    assert details["item"] == {
        "id": 42,
        "area_path_id": area_path_id,
        "title": "Current title",
        "work_item_type": "Bug",
        "state": "Active",
        "assigned_to": "Alice",
        "changed_date": datetime.datetime(2026, 7, 10, 12, 0),
        "parent_id": 7,
        "raw_json": {"fields": {"System.State": "Active"}},
        "synced_at": datetime.datetime(2026, 7, 10, 12, 1),
        "start_date": datetime.datetime(2026, 7, 1),
        "target_date": datetime.datetime(2026, 8, 1),
        "created_date": datetime.datetime(2026, 6, 1),
        "activated_date": datetime.datetime(2026, 6, 2),
        "closed_date": None,
    }
    assert details["history"] == [
        {
            "work_item_id": 42,
            "area_path_id": area_path_id,
            "rev": 1,
            "revised_by": "alice@example.com",
            "revised_date": datetime.datetime(2026, 7, 1, 10, 0),
            "raw_json": {"rev": 1},
            "synced_at": datetime.datetime(2026, 7, 1, 10, 1),
        },
        {
            "work_item_id": 42,
            "area_path_id": area_path_id,
            "rev": 2,
            "revised_by": "bob@example.com",
            "revised_date": datetime.datetime(2026, 7, 2, 10, 0),
            "raw_json": {"rev": 2},
            "synced_at": datetime.datetime(2026, 7, 2, 10, 1),
        },
    ]


def test_get_work_item_details_returns_none_for_missing_item(db_conn):
    assert repo.get_work_item_details(db_conn, work_item_id=999) is None


def test_get_capacity_snapshot_returns_only_the_requested_area_snapshot(db_conn):
    selected_area_path_id = _seed_area_path(db_conn, area_path="proj\\A")
    other_area_path_id = _seed_area_path(db_conn, area_path="proj\\B")
    _seed_capacity_snapshot(
        db_conn,
        selected_area_path_id,
        "2026-07-27T15:30:00",
        {"throughput": 8, "periods": [{"year": 2026, "quarter": 3}]},
    )
    _seed_capacity_snapshot(
        db_conn,
        other_area_path_id,
        "2026-07-27T16:00:00",
        {"throughput": 99},
    )

    snapshot = repo.get_capacity_snapshot(
        db_conn, area_path_id=selected_area_path_id
    )

    assert snapshot == {
        "generated_at": datetime.datetime(2026, 7, 27, 15, 30),
        "payload": {"throughput": 8, "periods": [{"year": 2026, "quarter": 3}]},
    }


def test_get_capacity_snapshot_returns_none_when_the_area_has_no_snapshot(db_conn):
    area_path_id = _seed_area_path(db_conn)

    assert repo.get_capacity_snapshot(db_conn, area_path_id=area_path_id) is None


def test_sqlite_connection_initializes_capacity_snapshots_schema(tmp_path):
    conn = SQLiteConnection(tmp_path / "api-read.db")
    conn.init_schema()

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = %s",
                ("capacity_snapshots",),
            )
            assert cur.fetchone()[0] == "capacity_snapshots"
    finally:
        conn.close()


def test_get_capacity_snapshot_parses_sqlite_json_payload(tmp_path):
    conn = SQLiteConnection(tmp_path / "api-read.db")
    conn.init_schema()
    conn.connection.execute(
        "INSERT INTO capacity_snapshots (area_path_id, generated_at, payload) VALUES (?, ?, ?)",
        (7, "2026-07-27T15:30:00", '{"throughput": 8}'),
    )
    conn.commit()

    try:
        assert repo.get_capacity_snapshot(conn, area_path_id=7) == {
            "generated_at": "2026-07-27T15:30:00",
            "payload": {"throughput": 8},
        }
    finally:
        conn.close()
