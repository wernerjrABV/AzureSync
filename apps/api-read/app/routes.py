from pathlib import Path
from datetime import date, datetime

from flask import Flask, g, jsonify, request, send_from_directory
from flask.json.provider import DefaultJSONProvider

from app import db, repository as repo
from app.config import get_cors_allowed_origins, get_web_dist_path
from app.sync_service_client import SyncServiceClient, SyncServiceUnavailable


class ISODateJSONProvider(DefaultJSONProvider):
    """Serializes datetime/date objects as ISO 8601 strings.

    Flask's DefaultJSONProvider (via Werkzeug's http_date) renders
    datetime/date objects as RFC 1123 strings (e.g. "Sat, 10 Jan 2026
    00:00:00 GMT"). The frontend expects ISO 8601 (e.g.
    "2026-01-10T00:00:00"), so this provider overrides that behavior
    while falling back to the default provider for everything else.
    """

    @staticmethod
    def default(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        return DefaultJSONProvider.default(obj)


def create_app(
    conn_factory=db.get_connection,
    sync_service_client=None,
    web_dist_path: str | Path | None = None,
) -> Flask:
    app = Flask(__name__, static_folder=None)
    sync_service_client = sync_service_client or SyncServiceClient()
    web_root = _resolve_web_root(web_dist_path)

    def open_connection():
        conn = conn_factory()
        g.setdefault("request_connections", []).append(conn)
        return conn

    @app.teardown_request
    def close_connections(_error):
        for conn in g.pop("request_connections", []):
            if getattr(conn, "is_sqlite", False):
                conn.close()
    app.json = ISODateJSONProvider(app)

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin")
        if origin in get_cors_allowed_origins():
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    def forward_to_sync_service(method: str, path: str, json_body=None):
        try:
            upstream = sync_service_client.request(method, path, json_body)
        except SyncServiceUnavailable:
            return jsonify({"error": "sync service unavailable"}), 503
        if upstream.json_body is None:
            return "", upstream.status_code
        return jsonify(upstream.json_body), upstream.status_code

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})

    @app.route("/api/area-paths", methods=["GET"])
    def list_area_paths():
        conn = open_connection()
        rows = repo.list_area_paths(conn)
        return jsonify(rows)

    @app.route("/api/area-paths", methods=["POST"])
    def create_area_path():
        return forward_to_sync_service(
            "POST", "/api/area-paths", request.get_json(silent=True)
        )

    @app.route("/api/area-paths/<int:area_path_id>", methods=["PUT"])
    def update_area_path(area_path_id):
        return forward_to_sync_service(
            "PUT",
            f"/api/area-paths/{area_path_id}",
            request.get_json(silent=True),
        )

    @app.route("/api/area-paths/<int:area_path_id>", methods=["DELETE"])
    def delete_area_path(area_path_id):
        return forward_to_sync_service("DELETE", f"/api/area-paths/{area_path_id}")

    @app.route("/api/area-paths/<int:area_path_id>/sync", methods=["POST"])
    def sync_area_path(area_path_id):
        return forward_to_sync_service(
            "POST", f"/api/area-paths/{area_path_id}/sync"
        )

    @app.route("/api/settings/azure-devops", methods=["GET"])
    def get_azure_devops_credential():
        return forward_to_sync_service("GET", "/api/settings/azure-devops")

    @app.route("/api/settings/azure-devops", methods=["PUT"])
    def put_azure_devops_credential():
        return forward_to_sync_service(
            "PUT", "/api/settings/azure-devops", request.get_json(silent=True)
        )

    @app.route("/api/settings/azure-devops", methods=["DELETE"])
    def delete_azure_devops_credential():
        return forward_to_sync_service("DELETE", "/api/settings/azure-devops")


    @app.route("/api/work-items", methods=["GET"])
    def list_work_items():
        conn = open_connection()
        try:
            area_path_id = request.args.get("area_path_id", type=int)
            search = request.args.get("search")
            page = request.args.get("page", default=1, type=int)
            page_size = request.args.get("page_size", default=50, type=int)
            order_by = request.args.get("order_by", default="changed_date")
            order_dir = request.args.get("order_dir", default="desc")

            rows, total = repo.list_work_items(
                conn,
                area_path_id=area_path_id,
                search=search,
                page=page,
                page_size=page_size,
                order_by=order_by,
                order_dir=order_dir,
            )
        except repo.InvalidQueryParam as exc:
            return jsonify({"error": str(exc)}), 400

        return jsonify(
            {
                "data": rows,
                "pagination": {"page": page, "page_size": page_size, "total": total},
            }
        )

    @app.route("/api/work-items/<int:work_item_id>", methods=["GET"])
    def get_work_item_details(work_item_id):
        conn = open_connection()
        details = repo.get_work_item_details(conn, work_item_id=work_item_id)
        if details is None:
            return jsonify({"error": "work item not found"}), 404
        return jsonify({"data": details})

    @app.route("/api/features-tree", methods=["GET"])
    def list_features_tree():
        area_path_id = request.args.get("area_path_id", type=int)
        if area_path_id is None:
            return jsonify({"error": "area_path_id is required"}), 400

        conn = open_connection()
        rows = repo.list_features_tree(conn, area_path_id=area_path_id)
        return jsonify({"data": rows})

    @app.route("/api/capacity", methods=["GET"])
    def get_capacity():
        area_path_id = request.args.get("area_path_id", type=int)
        year_text = request.args.get("year")
        quarter = request.args.get("quarter", type=int)

        if (
            area_path_id is None
            or area_path_id < 1
            or year_text is None
            or not (year_text.isascii() and year_text.isdecimal() and len(year_text) == 4)
            or quarter is None
            or quarter not in range(1, 5)
        ):
            return jsonify({"error": "area_path_id, year, and quarter are required and must be valid"}), 400

        conn = open_connection()
        snapshot = repo.get_capacity_snapshot(conn, area_path_id=area_path_id)
        if snapshot is None:
            return jsonify({"data": None})

        return jsonify(
            {
                "data": {
                    **snapshot["payload"],
                    "selected_period": {"year": int(year_text), "quarter": quarter},
                }
            }
        )

    if web_root is not None:

        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def serve_web(path: str):
            if path == "api" or path.startswith("api/"):
                return jsonify({"error": "not found"}), 404
            if path and (web_root / path).is_file():
                return send_from_directory(web_root, path)
            return send_from_directory(web_root, "index.html")

    return app


def _resolve_web_root(web_dist_path: str | Path | None) -> Path | None:
    configured_path = web_dist_path or get_web_dist_path()
    if configured_path is None:
        return None

    web_root = Path(configured_path).resolve()
    if not web_root.exists() or not web_root.is_dir():
        raise ValueError(f"Web dist path does not exist: {web_root}")

    return web_root
