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

    response = client.get("/api/work-items")

    assert response.status_code == 200
    body = response.get_json()
    assert body["pagination"] == {"page": 1, "page_size": 50, "total": 1}
    assert body["data"][0]["id"] == 1


def test_list_work_items_rejects_invalid_order_by(client, db_conn):
    response = client.get("/api/work-items?order_by=raw_json")

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
