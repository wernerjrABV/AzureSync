from flask import Flask, g, redirect, render_template, request

from app import db, repository as repo, sync_service
from app.ado_client import AdoClient


def create_app(conn_factory=db.get_connection) -> Flask:
    app = Flask(__name__)

    def open_connection():
        conn = conn_factory()
        g.setdefault("request_connections", []).append(conn)
        return conn

    @app.teardown_request
    def close_connections(_error):
        for conn in g.pop("request_connections", []):
            if getattr(conn, "is_sqlite", False):
                conn.close()

    @app.route("/", methods=["GET"])
    def index():
        conn = open_connection()
        rows = repo.list_area_paths(conn)
        auth_error = any(row["last_sync_status"] == "auth_error" for row in rows)
        return render_template("index.html", area_paths=rows, auth_error=auth_error)

    @app.route("/area-paths", methods=["POST"])
    def create_area_path():
        conn = open_connection()
        repo.create_area_path(
            conn,
            organization=request.form["organization"],
            project=request.form["project"],
            area_path=request.form["area_path"],
            incluir_subpaths=request.form.get("incluir_subpaths") == "on",
            ativo=request.form.get("ativo") == "on",
            intervalo_minutos=int(request.form.get("intervalo_minutos", 60)),
        )
        conn.commit()
        return redirect("/")

    @app.route("/area-paths/<int:area_path_id>/edit", methods=["GET"])
    def edit_area_path_form(area_path_id):
        conn = open_connection()
        rows = repo.list_area_paths(conn)
        editing = repo.get_area_path(conn, area_path_id)
        auth_error = any(row["last_sync_status"] == "auth_error" for row in rows)
        return render_template(
            "index.html", area_paths=rows, auth_error=auth_error, editing=editing
        )

    @app.route("/area-paths/<int:area_path_id>/edit", methods=["POST"])
    def edit_area_path(area_path_id):
        conn = open_connection()
        repo.update_area_path(
            conn,
            area_path_id,
            organization=request.form["organization"],
            project=request.form["project"],
            area_path=request.form["area_path"],
            incluir_subpaths=request.form.get("incluir_subpaths") == "on",
            ativo=request.form.get("ativo") == "on",
            intervalo_minutos=int(request.form.get("intervalo_minutos", 60)),
        )
        conn.commit()
        return redirect("/")

    @app.route("/area-paths/<int:area_path_id>/delete", methods=["POST"])
    def delete_area_path(area_path_id):
        conn = open_connection()
        repo.delete_area_path(conn, area_path_id)
        conn.commit()
        return redirect("/")

    @app.route("/area-paths/<int:area_path_id>/sync", methods=["POST"])
    def manual_sync(area_path_id):
        conn = open_connection()
        row = repo.get_area_path(conn, area_path_id)
        if row["is_running"]:
            return {"error": "sync already running"}, 409

        client = AdoClient(row["organization"], row["project"])
        result = sync_service.run_sync(conn, row, client)
        return redirect("/")

    return app
