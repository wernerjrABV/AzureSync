from datetime import date, datetime

from flask import Flask, jsonify, request
from flask.json.provider import DefaultJSONProvider

from app import db, repository as repo
from app.config import get_cors_allowed_origins


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


def create_app(conn_factory=db.get_connection) -> Flask:
    app = Flask(__name__)
    app.json = ISODateJSONProvider(app)

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin")
        if origin in get_cors_allowed_origins():
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET"
        return response

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"})

    @app.route("/api/area-paths", methods=["GET"])
    def list_area_paths():
        conn = conn_factory()
        rows = repo.list_area_paths(conn)
        return jsonify(rows)

    @app.route("/api/work-items", methods=["GET"])
    def list_work_items():
        conn = conn_factory()
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
        conn = conn_factory()
        details = repo.get_work_item_details(conn, work_item_id=work_item_id)
        if details is None:
            return jsonify({"error": "work item not found"}), 404
        return jsonify({"data": details})

    @app.route("/api/features-tree", methods=["GET"])
    def list_features_tree():
        area_path_id = request.args.get("area_path_id", type=int)
        if area_path_id is None:
            return jsonify({"error": "area_path_id is required"}), 400

        conn = conn_factory()
        rows = repo.list_features_tree(conn, area_path_id=area_path_id)
        return jsonify({"data": rows})

    return app
