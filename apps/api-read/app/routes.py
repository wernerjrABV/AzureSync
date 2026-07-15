from flask import Flask, jsonify, request

from app import db, repository as repo


def create_app(conn_factory=db.get_connection) -> Flask:
    app = Flask(__name__)

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
            work_item_type = request.args.get("work_item_type")
            page = request.args.get("page", default=1, type=int)
            page_size = request.args.get("page_size", default=50, type=int)
            order_by = request.args.get("order_by", default="changed_date")
            order_dir = request.args.get("order_dir", default="desc")

            rows, total = repo.list_work_items(
                conn,
                area_path_id=area_path_id,
                work_item_type=work_item_type,
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

    return app
