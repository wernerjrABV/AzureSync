from datetime import datetime
from contextlib import contextmanager
import json
from urllib.error import HTTPError

import pytest

from app import repository as repo
from app import update
from app.routes import create_app
from app.sync_service_client import (
    SyncServiceClient,
    SyncServiceResponse,
    SyncServiceUnavailable,
)


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


def test_update_status_returns_remote_version(monkeypatch):
    monkeypatch.setattr(
        update,
        "check_for_update",
        lambda: {
            "update_available": True,
            "current_version": "0.1.0",
            "latest_version": "0.2.0",
        },
    )
    app = create_app(conn_factory=lambda: None)
    app.config["TESTING"] = True

    with app.test_client() as test_client:
        response = test_client.get("/api/update")

    assert response.status_code == 200
    assert response.get_json()["update_available"] is True


def test_update_starts_background_update(monkeypatch):
    monkeypatch.setattr(
        update,
        "check_for_update",
        lambda: {
            "update_available": True,
            "current_version": "0.1.0",
            "latest_version": "0.2.0",
        },
    )
    started = []
    monkeypatch.setattr(update, "start_update", lambda: started.append(True))
    app = create_app(conn_factory=lambda: None)
    app.config["TESTING"] = True

    with app.test_client() as test_client:
        response = test_client.post("/api/update")

    assert response.status_code == 202
    assert response.get_json()["status"] == "started"
    assert started == [True]


def test_health_includes_cors_header_for_allowed_origin(client):
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"


def test_health_omits_cors_header_for_disallowed_origin(client):
    response = client.get("/health", headers={"Origin": "http://evil.example.com"})

    assert "Access-Control-Allow-Origin" not in response.headers


def test_serves_production_spa_and_preserves_api_routes(tmp_path):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<main>AzureSync portable</main>", encoding="utf-8")
    (web / "assets" / "app.js").write_text("window.portable = true", encoding="utf-8")
    app = create_app(conn_factory=lambda: None, web_dist_path=web)
    app.config["TESTING"] = True

    with app.test_client() as test_client:
        assert b"AzureSync portable" in test_client.get("/").data
        assert b"AzureSync portable" in test_client.get("/synchronization").data
        assert b"window.portable" in test_client.get("/assets/app.js").data
        assert test_client.get("/health").get_json() == {"status": "ok"}
        assert test_client.get("/api/not-a-route").status_code == 404


def test_create_app_rejects_missing_web_dist_directory(tmp_path):
    missing_web = tmp_path / "missing-web"

    with pytest.raises(ValueError) as excinfo:
        create_app(conn_factory=lambda: None, web_dist_path=missing_web)

    assert str(missing_web) in str(excinfo.value)


def _seed_capacity_snapshot(conn, *, area_path_id, payload):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO capacity_snapshots (area_path_id, generated_at, payload)
            VALUES (%s, %s, %s)
            """,
            (area_path_id, "2026-07-27T15:30:00", json.dumps(payload)),
        )
    conn.commit()


def test_get_capacity_returns_requested_area_snapshot_and_selected_period(client, db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s) RETURNING id",
            ("org", "proj", "proj\\A"),
        )
        selected_area_path_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s) RETURNING id",
            ("org", "proj", "proj\\B"),
        )
        other_area_path_id = cur.fetchone()[0]
    db_conn.commit()
    _seed_capacity_snapshot(
        db_conn,
        area_path_id=selected_area_path_id,
        payload={"forecast": {"expected": 48}, "generated_at": "2026-07-27T15:30:00"},
    )
    _seed_capacity_snapshot(
        db_conn,
        area_path_id=other_area_path_id,
        payload={"forecast": {"expected": 99}},
    )

    response = client.get(
        f"/api/capacity?area_path_id={selected_area_path_id}&year=2026&quarter=3"
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "data": {
            "forecast": {"expected": 48},
            "generated_at": "2026-07-27T15:30:00",
            "selected_period": {"year": 2026, "quarter": 3},
        }
    }


def test_get_capacity_returns_null_for_an_area_without_snapshot(client, db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s) RETURNING id",
            ("org", "proj", "proj\\A"),
        )
        area_path_id = cur.fetchone()[0]
    db_conn.commit()

    response = client.get(f"/api/capacity?area_path_id={area_path_id}&year=2026&quarter=3")

    assert response.status_code == 200
    assert response.get_json() == {"data": None}


@pytest.mark.parametrize(
    "query",
    [
        "year=2026&quarter=3",
        "area_path_id=1&quarter=3",
        "area_path_id=1&year=not-a-year&quarter=3",
        "area_path_id=1&year=2026&quarter=not-a-quarter",
        "area_path_id=1&year=2026&quarter=0",
        "area_path_id=1&year=2026&quarter=5",
    ],
)
def test_get_capacity_rejects_missing_or_invalid_parameters(client, query):
    response = client.get(f"/api/capacity?{query}")

    assert response.status_code == 400


def test_get_capacity_rejects_unicode_digit_year_before_reading_snapshot(client, db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO area_paths (organization, project, area_path) VALUES (%s, %s, %s) RETURNING id",
            ("org", "proj", "proj\\A"),
        )
        area_path_id = cur.fetchone()[0]
    db_conn.commit()
    _seed_capacity_snapshot(db_conn, area_path_id=area_path_id, payload={"forecast": {}})

    response = client.get(
        f"/api/capacity?area_path_id={area_path_id}&year=%C2%B2%C2%B2%C2%B2%C2%B2&quarter=3"
    )

    assert response.status_code == 400


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


def test_create_area_path_forwards_json_to_sync_service():
    class RecordingSyncServiceClient:
        def __init__(self):
            self.calls = []

        def request(self, method, path, json_body=None):
            self.calls.append((method, path, json_body))
            return SyncServiceResponse(
                status_code=201,
                json_body={"data": {"id": 17, **json_body}},
            )

    sync_service_client = RecordingSyncServiceClient()
    app = create_app(
        conn_factory=lambda: None,
        sync_service_client=sync_service_client,
    )
    app.config["TESTING"] = True
    payload = {"organization": "org", "project": "proj", "area_path": "proj\\A"}

    with app.test_client() as test_client:
        response = test_client.post("/api/area-paths", json=payload)

    assert response.status_code == 201
    assert response.get_json() == {"data": {"id": 17, **payload}}
    assert sync_service_client.calls == [("POST", "/api/area-paths", payload)]


@pytest.mark.parametrize(
    ("method", "path", "payload", "upstream_status", "upstream_body"),
    [
        (
            "PUT",
            "/api/area-paths/7",
            {"organization": "org", "project": "proj", "area_path": "proj\\B"},
            404,
            {"error": "area path not found"},
        ),
        (
            "DELETE",
            "/api/area-paths/7",
            None,
            204,
            None,
        ),
        (
            "POST",
            "/api/area-paths/7/sync",
            None,
            202,
            {"status": "started"},
        ),
        (
            "POST",
            "/api/area-paths/7/sync",
            None,
            409,
            {"error": "sync already running"},
        ),
        (
            "POST",
            "/api/area-paths/7/sync",
            None,
            502,
            {"error": "upstream sync failed"},
        ),
        (
            "GET",
            "/api/settings/azure-devops",
            None,
            200,
            {"configured": True, "updated_at": "2026-08-18T12:00:00"},
        ),
        (
            "PUT",
            "/api/settings/azure-devops",
            {"api_key": "browser-secret"},
            200,
            {"configured": True, "updated_at": "2026-08-18T12:00:00"},
        ),
        (
            "DELETE",
            "/api/settings/azure-devops",
            None,
            204,
            None,
        ),
    ],
)
def test_area_path_mutations_forward_upstream_status_and_json_verbatim(
    method, path, payload, upstream_status, upstream_body
):
    class StaticSyncServiceClient:
        def __init__(self):
            self.calls = []

        def request(self, request_method, request_path, json_body=None):
            self.calls.append((request_method, request_path, json_body))
            return SyncServiceResponse(upstream_status, upstream_body)

    sync_service_client = StaticSyncServiceClient()
    app = create_app(
        conn_factory=lambda: None,
        sync_service_client=sync_service_client,
    )
    app.config["TESTING"] = True

    with app.test_client() as test_client:
        response = test_client.open(path, method=method, json=payload)

    assert response.status_code == upstream_status
    assert response.get_json() == upstream_body
    assert sync_service_client.calls == [(method, path, payload)]
    if method == "PUT":
        assert "browser-secret" not in response.get_data(as_text=True)


def test_area_path_write_returns_503_when_sync_service_is_unavailable():
    class UnavailableSyncServiceClient:
        def request(self, *_args, **_kwargs):
            raise SyncServiceUnavailable()

    app = create_app(
        conn_factory=lambda: None,
        sync_service_client=UnavailableSyncServiceClient(),
    )
    app.config["TESTING"] = True

    with app.test_client() as test_client:
        response = test_client.post(
            "/api/area-paths",
            json={"organization": "org", "project": "proj", "area_path": "proj\\A"},
        )

    assert response.status_code == 503
    assert response.get_json() == {"error": "sync service unavailable"}


def test_azure_devops_settings_read_returns_503_when_sync_service_is_unavailable():
    class UnavailableSyncServiceClient:
        def request(self, *_args, **_kwargs):
            raise SyncServiceUnavailable()

    app = create_app(
        conn_factory=lambda: None,
        sync_service_client=UnavailableSyncServiceClient(),
    )
    app.config["TESTING"] = True

    with app.test_client() as test_client:
        response = test_client.get("/api/settings/azure-devops")

    assert response.status_code == 503
    assert response.get_json() == {"error": "sync service unavailable"}


def test_cors_preflight_allows_area_path_write_methods():
    app = create_app(conn_factory=lambda: None)
    app.config["TESTING"] = True

    with app.test_client() as test_client:
        response = test_client.options(
            "/api/area-paths",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert response.headers["Access-Control-Allow-Methods"] == "GET, POST, PUT, DELETE, OPTIONS"
    assert response.headers["Access-Control-Allow-Headers"] == "Content-Type"


def test_sync_service_client_posts_json_to_configured_base_url(monkeypatch):
    captured = {}

    class FakeHTTPResponse:
        status = 202

        def read(self):
            return b'{"status": "started"}'

    @contextmanager
    def fake_urlopen(request):
        captured["url"] = request.full_url
        captured["method"] = request.method
        captured["data"] = request.data
        captured["content_type"] = request.headers["Content-type"]
        yield FakeHTTPResponse()

    monkeypatch.setattr("app.sync_service_client.urlopen", fake_urlopen)
    client = SyncServiceClient("http://sync-service:5000/")

    response = client.request(
        "POST", "/api/area-paths", {"organization": "org", "project": "proj"}
    )

    assert response == SyncServiceResponse(202, {"status": "started"})
    assert captured == {
        "url": "http://sync-service:5000/api/area-paths",
        "method": "POST",
        "data": b'{"organization": "org", "project": "proj"}',
        "content_type": "application/json",
    }


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
    body = response.get_json()
    item_synced_at = body["data"]["item"].pop("synced_at")
    history_synced_at = body["data"]["history"][0].pop("synced_at")
    assert body == {
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
                }
            ],
        }
    }
    assert datetime.fromisoformat(item_synced_at)
    assert datetime.fromisoformat(history_synced_at)


def test_get_work_item_details_not_found(client):
    response = client.get("/api/work-items/999")

    assert response.status_code == 404
    assert response.get_json() == {"error": "work item not found"}
