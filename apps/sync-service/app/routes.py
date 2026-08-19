import datetime
import threading
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, g, redirect, render_template, request

from app import credentials, db, repository as repo, sync_service
from app.ado_client import AdoClient
from app.credential_protection import CredentialProtectionError, DpapiCredentialProtector


_AREA_PATH_RESPONSE_FIELDS = (
    "id",
    "organization",
    "project",
    "area_path",
    "incluir_subpaths",
    "ativo",
    "intervalo_minutos",
    "is_running",
    "last_sync_at",
    "last_sync_status",
    "last_sync_count",
    "last_error_msg",
    "created_at",
    "history_loaded_at",
)
_BOOLEAN_RESPONSE_FIELDS = {"incluir_subpaths", "ativo", "is_running"}
_MANUAL_SYNC_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="manual-sync")
_MANUAL_SYNC_IDS: set[int] = set()
_MANUAL_SYNC_LOCK = threading.Lock()


def start_manual_sync(conn_factory, area_path_id: int, credential_protector) -> bool:
    with _MANUAL_SYNC_LOCK:
        if area_path_id in _MANUAL_SYNC_IDS:
            return False
        _MANUAL_SYNC_IDS.add(area_path_id)
        try:
            _MANUAL_SYNC_EXECUTOR.submit(
                _run_manual_sync_worker,
                conn_factory,
                area_path_id,
                credential_protector,
            )
        except Exception:
            _MANUAL_SYNC_IDS.discard(area_path_id)
            raise
    return True


def _run_manual_sync_worker(conn_factory, area_path_id: int, credential_protector) -> None:
    conn = None
    try:
        conn = conn_factory()
        row = repo.get_area_path(conn, area_path_id)
        if row is None or row["is_running"]:
            return
        client = AdoClient(
            row["organization"],
            row["project"],
            pat_provider=lambda: credentials.load_api_key(conn, credential_protector),
        )
        sync_service.run_sync(conn, row, client)
    finally:
        with _MANUAL_SYNC_LOCK:
            _MANUAL_SYNC_IDS.discard(area_path_id)
        if conn is not None and getattr(conn, "is_sqlite", False):
            conn.close()


def _serialize_area_path(row: dict) -> dict:
    serialized = {}
    for field in _AREA_PATH_RESPONSE_FIELDS:
        value = row.get(field)
        if isinstance(value, (datetime.datetime, datetime.date)):
            value = value.isoformat()
        elif field in _BOOLEAN_RESPONSE_FIELDS and value is not None:
            value = bool(value)
        serialized[field] = value
    return serialized


def _serialize_credential_status(status):
    return {
        "configured": status.configured,
        "updated_at": status.updated_at.isoformat() if status.updated_at else None,
    }


def _parse_area_path_payload():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None

    fields = {}
    for field in ("organization", "project", "area_path"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return None
        fields[field] = value.strip()

    interval = payload.get("intervalo_minutos", 60)
    if isinstance(interval, bool) or not isinstance(interval, int) or interval <= 0:
        return None
    fields["intervalo_minutos"] = interval

    for field, default in (("incluir_subpaths", True), ("ativo", True)):
        value = payload.get(field, default)
        if not isinstance(value, bool):
            return None
        fields[field] = value
    return fields


def create_app(conn_factory=db.get_connection, credential_protector=None) -> Flask:
    app = Flask(__name__)
    credential_protector = credential_protector or DpapiCredentialProtector()

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

    @app.route("/api/area-paths", methods=["GET"])
    def list_area_paths_api():
        conn = open_connection()
        return {"data": [_serialize_area_path(row) for row in repo.list_area_paths(conn)]}

    @app.route("/api/area-paths", methods=["POST"])
    def create_area_path_api():
        fields = _parse_area_path_payload()
        if fields is None:
            return {"error": "invalid area path payload"}, 400

        conn = open_connection()
        area_path_id = repo.create_area_path(conn, **fields)
        conn.commit()
        return {"data": _serialize_area_path(repo.get_area_path(conn, area_path_id))}, 201

    @app.route("/api/area-paths/<int:area_path_id>", methods=["PUT"])
    def update_area_path_api(area_path_id):
        fields = _parse_area_path_payload()
        if fields is None:
            return {"error": "invalid area path payload"}, 400

        conn = open_connection()
        if repo.get_area_path(conn, area_path_id) is None:
            return {"error": "area path not found"}, 404
        repo.update_area_path(conn, area_path_id, **fields)
        conn.commit()
        return {"data": _serialize_area_path(repo.get_area_path(conn, area_path_id))}

    @app.route("/api/area-paths/<int:area_path_id>", methods=["DELETE"])
    def delete_area_path_api(area_path_id):
        conn = open_connection()
        if repo.get_area_path(conn, area_path_id) is None:
            return {"error": "area path not found"}, 404
        repo.delete_area_path(conn, area_path_id)
        conn.commit()
        return "", 204

    @app.route("/api/area-paths/<int:area_path_id>/sync", methods=["POST"])
    def manual_sync_api(area_path_id):
        conn = open_connection()
        row = repo.get_area_path(conn, area_path_id)
        if row is None:
            return {"error": "area path not found"}, 404
        if row["is_running"]:
            return {"error": "sync already running"}, 409
        try:
            started = start_manual_sync(conn_factory, area_path_id, credential_protector)
        except Exception:
            return {"error": "sync could not be queued"}, 503
        if not started:
            return {"error": "sync already running"}, 409
        return {"status": "started"}, 202

    @app.route("/api/settings/azure-devops", methods=["GET"])
    def get_azure_devops_credential_api():
        conn = open_connection()
        return _serialize_credential_status(credentials.get_status(conn))

    @app.route("/api/settings/azure-devops", methods=["PUT"])
    def put_azure_devops_credential_api():
        payload = request.get_json(silent=True)
        api_key = payload.get("api_key") if isinstance(payload, dict) else None

        conn = open_connection()
        try:
            status = credentials.save_api_key(conn, credential_protector, api_key)
            conn.commit()
        except credentials.CredentialValidationError:
            conn.rollback()
            return {"error": "invalid Azure DevOps credential"}, 400
        except CredentialProtectionError:
            conn.rollback()
            return {"error": "credential could not be stored"}, 500
        return _serialize_credential_status(status)

    @app.route("/api/settings/azure-devops", methods=["DELETE"])
    def delete_azure_devops_credential_api():
        conn = open_connection()
        credentials.delete_api_key(conn)
        conn.commit()
        return "", 204

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

        client = AdoClient(
            row["organization"],
            row["project"],
            pat_provider=lambda: credentials.load_api_key(conn, credential_protector),
        )
        result = sync_service.run_sync(conn, row, client)
        return redirect("/")

    return app
