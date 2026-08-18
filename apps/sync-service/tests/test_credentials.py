import base64
import datetime

import pytest

from app import db
from app import repository as repo
from app.credential_protection import CredentialProtectionError
from app.credentials import (
    AzureDevOpsCredentialStatus,
    CredentialValidationError,
)
from app import credentials


class PrefixProtector:
    def protect(self, plaintext: str) -> str:
        return base64.b64encode(f"protected:{plaintext}".encode("utf-8")).decode(
            "ascii"
        )

    def unprotect(self, protected_value: str) -> str:
        prefix = "protected:"
        decoded = base64.b64decode(protected_value, validate=True).decode("utf-8")
        if not decoded.startswith(prefix):
            raise CredentialProtectionError("stored credential cannot be decrypted")
        return decoded[len(prefix) :]


def test_save_load_status_replace_and_delete_api_key(tmp_path):
    conn = db.SQLiteConnection(str(tmp_path / "credentials.sqlite3"))
    db.init_schema(conn)
    protector = PrefixProtector()
    saved_at = datetime.datetime(2026, 8, 18, 12, 0)

    assert credentials.get_status(conn) == AzureDevOpsCredentialStatus(False, None)

    credentials.save_api_key(
        conn, protector, "first-secret", now_factory=lambda: saved_at
    )
    conn.commit()

    assert credentials.load_api_key(conn, protector) == "first-secret"
    assert credentials.get_status(conn) == AzureDevOpsCredentialStatus(True, saved_at)
    assert repo.get_app_setting(conn, credentials.SETTING_KEY) == {
        "key": credentials.SETTING_KEY,
        "encrypted_value": "cHJvdGVjdGVkOmZpcnN0LXNlY3JldA==",
        "updated_at": saved_at,
    }

    credentials.save_api_key(
        conn,
        protector,
        "second-secret",
        now_factory=lambda: saved_at + datetime.timedelta(minutes=5),
    )
    conn.commit()

    assert credentials.load_api_key(conn, protector) == "second-secret"

    credentials.delete_api_key(conn)
    conn.commit()

    assert credentials.load_api_key(conn, protector) is None
    assert credentials.get_status(conn) == AzureDevOpsCredentialStatus(False, None)
    conn.close()


class TrackingProtector:
    def __init__(self) -> None:
        self.calls = []

    def protect(self, plaintext: str) -> str:
        self.calls.append(plaintext)
        return base64.b64encode(f"protected:{plaintext}".encode("utf-8")).decode(
            "ascii"
        )

    def unprotect(self, protected_value: str) -> str:
        raise AssertionError("unprotect should not be called in validation tests")


@pytest.mark.parametrize(
    "api_key",
    [
        "",
        "   \t  ",
        1234,
        "x" * 4097,
    ],
)
def test_save_api_key_rejects_invalid_values_before_protection(tmp_path, api_key):
    conn = db.SQLiteConnection(str(tmp_path / "validation.sqlite3"))
    db.init_schema(conn)
    protector = TrackingProtector()

    with pytest.raises(
        CredentialValidationError, match="invalid Azure DevOps credential"
    ):
        credentials.save_api_key(conn, protector, api_key)

    assert protector.calls == []
    assert credentials.get_status(conn) == AzureDevOpsCredentialStatus(False, None)
    conn.close()
