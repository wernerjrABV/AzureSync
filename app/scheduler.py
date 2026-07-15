import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app import db, repository as repo, sync_service
from app.ado_client import AdoClient

JOB_ID_PREFIX = "sync-area-path-"


def _sync_all_active(conn_factory):
    conn = conn_factory()
    now = datetime.datetime.now()
    for row in repo.list_area_paths(conn):
        if not row["ativo"]:
            continue
        if row["last_sync_at"]:
            due_at = row["last_sync_at"] + datetime.timedelta(minutes=row["intervalo_minutos"])
            if now < due_at:
                continue
        client = AdoClient(row["organization"], row["project"])
        sync_service.run_sync(conn, row, client)


def build_scheduler(conn_factory=db.get_connection) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _sync_all_active,
        "interval",
        minutes=1,
        args=[conn_factory],
        id="sync-tick",
        replace_existing=True,
    )
    return scheduler
