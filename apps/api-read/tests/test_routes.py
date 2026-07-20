import pytest

from app import repository as repo
from app.routes import create_app


@pytest.fixture
def client(db_conn):
    app = create_app(conn_factory=lambda: db_conn)
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_health_includes_cors_header_for_allowed_origin(client):
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"


def test_health_omits_cors_header_for_disallowed_origin(client):
    response = client.get("/health", headers={"Origin": "http://evil.example.com"})

    assert "Access-Control-Allow-Origin" not in response.headers


def test_list_area_paths(client, db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s)",
            ("org", "proj", "proj\\A"),
        )
    db_conn.commit()

    response = client.get("/api/area-paths")

    assert response.status_code == 200
    body = response.get_json()
    assert body[0]["area_path"] == "proj\\A"


def test_list_work_items_default_envelope(client, db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s) RETURNING id",
            ("org", "proj", "proj\\A"),
        )
        area_path_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO work_items (id, area_path_id, title, work_item_type, state, changed_date, raw_json)
            VALUES (1, %s, 'Item 1', 'Bug', 'Active', '2026-01-01T00:00:00', '{}')
            """,
            (area_path_id,),
        )
    db_conn.commit()

    response = client.get(f"/api/work-items?area_path_id={area_path_id}")

    assert response.status_code == 200
    body = response.get_json()
    assert body["pagination"] == {"page": 1, "page_size": 50, "total": 1}
    assert body["data"][0]["id"] == 1


def test_list_work_items_requires_area_path_id(client, db_conn):
    response = client.get("/api/work-items")

    assert response.status_code == 400
    assert response.get_json() == {"error": "area_path_id is required"}


def test_list_work_items_search_param(client, db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s) RETURNING id",
            ("org", "proj", "proj\\A"),
        )
        area_path_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO work_items (id, area_path_id, title, work_item_type, state, changed_date, raw_json) VALUES (1, %s, 'Login bug', 'Bug', 'Active', '2026-01-01T00:00:00', '{}')",
            (area_path_id,),
        )
        cur.execute(
            "INSERT INTO work_items (id, area_path_id, title, work_item_type, state, changed_date, raw_json) VALUES (2, %s, 'Export feature', 'Task', 'Active', '2026-01-01T00:00:00', '{}')",
            (area_path_id,),
        )
    db_conn.commit()

    response = client.get(f"/api/work-items?area_path_id={area_path_id}&search=login")

    body = response.get_json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["id"] == 1


def test_list_work_items_rejects_invalid_order_by(client, db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s) RETURNING id",
            ("org", "proj", "proj\\A"),
        )
        area_path_id = cur.fetchone()[0]
    db_conn.commit()

    response = client.get(f"/api/work-items?area_path_id={area_path_id}&order_by=raw_json")

    assert response.status_code == 400


def test_list_work_items_filters_by_area_path_id(client, db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s) RETURNING id",
            ("org", "proj", "proj\\A"),
        )
        ap1 = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s) RETURNING id",
            ("org", "proj", "proj\\B"),
        )
        ap2 = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO work_items (id, area_path_id, title, work_item_type, state, changed_date, raw_json) VALUES (1, %s, 'A', 'Bug', 'Active', '2026-01-01T00:00:00', '{}')",
            (ap1,),
        )
        cur.execute(
            "INSERT INTO work_items (id, area_path_id, title, work_item_type, state, changed_date, raw_json) VALUES (2, %s, 'B', 'Bug', 'Active', '2026-01-01T00:00:00', '{}')",
            (ap2,),
        )
    db_conn.commit()

    response = client.get(f"/api/work-items?area_path_id={ap1}")

    body = response.get_json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["id"] == 1


def test_list_features_tree_returns_envelope(client, db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s) RETURNING id",
            ("org", "proj", "proj\\A"),
        )
        area_path_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO work_items (id, area_path_id, title, work_item_type, state, parent_id, start_date, target_date, raw_json)
            VALUES (1, %s, 'Feat A', 'Feature', 'Active', NULL, '2026-01-10T00:00:00', '2026-02-28T00:00:00', '{}')
            """,
            (area_path_id,),
        )
    db_conn.commit()

    response = client.get(f"/api/features-tree?area_path_id={area_path_id}")

    assert response.status_code == 200
    body = response.get_json()
    assert body["data"][0]["id"] == 1
    assert body["data"][0]["work_item_type"] == "Feature"
    assert body["data"][0]["start_date"] == "2026-01-10T00:00:00"
    assert body["data"][0]["target_date"] == "2026-02-28T00:00:00"


def test_list_features_tree_requires_area_path_id(client):
    response = client.get("/api/features-tree")

    assert response.status_code == 400
    assert response.get_json() == {"error": "area_path_id is required"}


def test_get_work_item_details(client, db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s) RETURNING id",
            ("org", "proj", "proj\\A"),
        )
        area_path_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO work_items (id, area_path_id, title, work_item_type, state, changed_date, raw_json)
            VALUES (42, %s, 'Current title', 'Bug', 'Active', '2026-07-10T12:00:00', '{}')
            """,
            (area_path_id,),
        )
        cur.execute(
            """
            INSERT INTO work_item_history
                (work_item_id, area_path_id, rev, revised_by, revised_date, raw_json)
            VALUES (42, %s, 1, 'alice@example.com', '2026-07-01T10:00:00', '{"rev": 1}')
            """,
            (area_path_id,),
        )
    db_conn.commit()

    response = client.get("/api/work-items/42")

    assert response.status_code == 200
    assert response.get_json() == {
        "data": {
            "item": {
                "id": 42,
                "area_path_id": area_path_id,
                "title": "Current title",
                "work_item_type": "Bug",
                "state": "Active",
                "assigned_to": None,
                "changed_date": "2026-07-10T12:00:00",
                "parent_id": None,
                "raw_json": {},
                "synced_at": None,
                "start_date": None,
                "target_date": None,
                "created_date": None,
                "activated_date": None,
                "closed_date": None,
            },
            "history": [
                {
                    "work_item_id": 42,
                    "area_path_id": area_path_id,
                    "rev": 1,
                    "revised_by": "alice@example.com",
                    "revised_date": "2026-07-01T10:00:00",
                    "raw_json": {"rev": 1},
                    "synced_at": None,
                }
            ],
        }
    }


def test_get_work_item_details_not_found(client):
    response = client.get("/api/work-items/999")

    assert response.status_code == 404
    assert response.get_json() == {"error": "work item not found"}
