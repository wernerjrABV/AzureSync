import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app import credentials, db, repository as repo, sync_control, sync_service
from app.ado_client import AdoClient
from app.credential_protection import DpapiCredentialProtector

JOB_ID_PREFIX = "sync-area-path-"


def _sync_all_active(conn_factory, credential_protector) -> None:
    conn = conn_factory()
    try:
        now = datetime.datetime.now()
        for row in repo.list_area_paths(conn):
            if not row["ativo"]:
                continue
            if row["last_sync_at"]:
                due_at = row["last_sync_at"] + datetime.timedelta(minutes=row["intervalo_minutos"])
                if now < due_at:
                    continue
            client = AdoClient(
                row["organization"],
                row["project"],
                pat_provider=lambda: credentials.load_api_key(conn, credential_protector),
            )
            sync_event = sync_control.register(row["id"])
            try:
                sync_service.run_sync(conn, row, client, should_cancel=sync_event.is_set)
            finally:
                if sync_control.take_deletion_request(row["id"]):
                    repo.delete_area_path(conn, row["id"])
                    conn.commit()
                sync_control.unregister(row["id"])
    finally:
        if getattr(conn, "is_sqlite", False):
            conn.close()


def build_scheduler(conn_factory=db.get_connection, credential_protector=None) -> BackgroundScheduler:
    credential_protector = credential_protector or DpapiCredentialProtector()
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _sync_all_active,
        "interval",
        minutes=1,
        args=[conn_factory, credential_protector],
        id="sync-tick",
        replace_existing=True,
    )
    return scheduler
