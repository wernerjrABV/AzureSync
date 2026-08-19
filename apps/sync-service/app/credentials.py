import datetime
from dataclasses import dataclass
from typing import Callable

from app import repository as repo
from app.credential_protection import CredentialProtector

SETTING_KEY = "azure_devops_api_key"
MAX_API_KEY_LENGTH = 4096


class CredentialValidationError(ValueError):
    pass


@dataclass(frozen=True)
class AzureDevOpsCredentialStatus:
    configured: bool
    updated_at: datetime.datetime | None


def get_status(conn) -> AzureDevOpsCredentialStatus:
    row = repo.get_app_setting(conn, SETTING_KEY)
    return AzureDevOpsCredentialStatus(
        configured=row is not None,
        updated_at=row["updated_at"] if row else None,
    )


def save_api_key(
    conn,
    protector: CredentialProtector,
    api_key: str,
    *,
    now_factory: Callable[[], datetime.datetime] = datetime.datetime.now,
) -> AzureDevOpsCredentialStatus:
    if (
        not isinstance(api_key, str)
        or not api_key.strip()
        or len(api_key) > MAX_API_KEY_LENGTH
    ):
        raise CredentialValidationError("invalid Azure DevOps credential")

    updated_at = now_factory()
    repo.upsert_app_setting(
        conn,
        key=SETTING_KEY,
        encrypted_value=protector.protect(api_key.strip()),
        updated_at=updated_at,
    )
    return AzureDevOpsCredentialStatus(True, updated_at)


def delete_api_key(conn) -> None:
    repo.delete_app_setting(conn, SETTING_KEY)


def load_api_key(conn, protector: CredentialProtector) -> str | None:
    row = repo.get_app_setting(conn, SETTING_KEY)
    return protector.unprotect(row["encrypted_value"]) if row else None
