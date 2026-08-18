import datetime
import base64
from unittest.mock import ANY, MagicMock, patch

from app import credentials, db, repository as repo, scheduler
from app.credential_protection import CredentialProtectionError


class PrefixProtector:
    def protect(self, plaintext: str) -> str:
        return base64.b64encode(f"protected:{plaintext}".encode("utf-8")).decode("ascii")

    def unprotect(self, protected_value: str) -> str:
        prefix = "protected:"
        decoded = base64.b64decode(protected_value, validate=True).decode("utf-8")
        if not decoded.startswith(prefix):
            raise CredentialProtectionError("stored credential cannot be decrypted")
        return decoded[len(prefix) :]


@patch("app.scheduler.sync_service.run_sync")
@patch("app.scheduler.AdoClient")
def test_sync_all_active_uses_saved_credential_provider_for_due_area(
    mock_ado_client, mock_run_sync, tmp_path
):
    sqlite_db_path = tmp_path / "scheduler.sqlite3"
    seed_conn = db.SQLiteConnection(sqlite_db_path)
    db.init_schema(seed_conn)
    protector = PrefixProtector()
    area_path_id = repo.create_area_path(seed_conn, "org", "proj", "proj\\A")
    credentials.save_api_key(seed_conn, protector, "scheduled-secret")
    seed_conn.commit()
    seed_conn.close()

    captured = {}
    fake_client = MagicMock(name="ado-client")

    def build_client(organization, project, **kwargs):
        captured["organization"] = organization
        captured["project"] = project
        captured["pat_provider"] = kwargs["pat_provider"]
        captured["resolved_pat"] = kwargs["pat_provider"]()
        return fake_client

    mock_ado_client.side_effect = build_client

    scheduler._sync_all_active(lambda: db.SQLiteConnection(sqlite_db_path), protector)

    assert captured == {
        "organization": "org",
        "project": "proj",
        "pat_provider": ANY,
        "resolved_pat": "scheduled-secret",
    }
    run_conn, run_row, run_client = mock_run_sync.call_args.args
    assert getattr(run_conn, "is_sqlite", False) is True
    assert run_row["id"] == area_path_id
    assert run_client is fake_client
