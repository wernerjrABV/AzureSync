# Azure DevOps Credential Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Azure DevOps PAT from `.env` to an Astryx synchronization-page workflow backed by DPAPI-encrypted database storage.

**Architecture:** `sync-service` owns the credential API, DPAPI coordination, database mutations, and credential use during manual and scheduled syncs. `api-read` forwards the public credential routes without adding write SQL, while `web-read` only receives status metadata and never receives the PAT or ciphertext.

**Tech Stack:** Python 3.12+, Flask 3.1, psycopg 3.3, SQLite, Windows DPAPI through `ctypes`, pytest 8.3, React 19, TypeScript, Vite 6, Vitest 4, Astryx Design System.

**Spec:** `docs/superpowers/specs/2026-08-18-windows-portable-distribution-and-credential-design.md`

## Global Constraints

- `apps/sync-service/` is the only database writer.
- `apps/sync-service/app/repository.py` is the only file that may issue write SQL.
- `create_app(conn_factory=...)` remains the supported request-scoped database test hook; new dependencies are optional injected parameters.
- `sync_service.run_sync` continues to own locking, checkpoint advancement, upserts, deletes, history backfill, rollback, and final status.
- Missing, unreadable, and rejected credentials must become `auth_error` from inside the execution covered by `sync_service.run_sync`.
- The PAT must not appear in `.env`, process arguments, environment variables, HTTP responses, frontend state after save, or logs.
- Persist only Base64-encoded DPAPI `CurrentUser` ciphertext under the stable key `azure_devops_api_key`.
- Reject API keys longer than 4,096 characters.
- The web UI must use only existing Astryx components; add no CSS, inline styles, styled-components, emotion, or non-Astryx visual components.
- Preserve PostgreSQL and SQLite behavior and the `api-read` read-only SQL guardrail.
- Follow TDD for every behavior change: write one focused failing test, observe the expected failure, implement the minimum behavior, and rerun the focused and regression tests.

---

### Task 1: Add the application-settings schema and repository boundary

**Files:**
- Modify: `apps/sync-service/app/db.py:7-166`
- Modify: `apps/sync-service/app/repository.py:1-260`
- Modify: `apps/sync-service/tests/test_db.py`
- Modify: `apps/sync-service/tests/test_sqlite_fallback.py`
- Modify: `apps/sync-service/tests/test_repository.py`

**Interfaces:**
- Produces `repo.get_app_setting(conn, key: str) -> dict | None`.
- Produces `repo.upsert_app_setting(conn, *, key: str, encrypted_value: str, updated_at: datetime.datetime) -> None`.
- Produces `repo.delete_app_setting(conn, key: str) -> None`.
- Produces table `app_settings(key TEXT PRIMARY KEY, encrypted_value TEXT NOT NULL, updated_at TIMESTAMP NOT NULL)` in both database backends.

- [ ] **Step 1: Write failing SQLite schema and repository tests**

Add this behavior to `test_sqlite_fallback.py` and `test_repository.py`:

```python
def test_sqlite_schema_persists_replaces_and_deletes_app_setting(tmp_path):
    conn = db.SQLiteConnection(str(tmp_path / "settings.sqlite3"))
    db.init_schema(conn)
    first = datetime.datetime(2026, 8, 18, 10, 0)
    second = datetime.datetime(2026, 8, 18, 11, 0)

    repo.upsert_app_setting(
        conn,
        key="azure_devops_api_key",
        encrypted_value="cipher-one",
        updated_at=first,
    )
    repo.upsert_app_setting(
        conn,
        key="azure_devops_api_key",
        encrypted_value="cipher-two",
        updated_at=second,
    )
    conn.commit()

    assert repo.get_app_setting(conn, "azure_devops_api_key") == {
        "key": "azure_devops_api_key",
        "encrypted_value": "cipher-two",
        "updated_at": second,
    }
    repo.delete_app_setting(conn, "azure_devops_api_key")
    conn.commit()
    assert repo.get_app_setting(conn, "azure_devops_api_key") is None
    conn.close()
```

Add a PostgreSQL schema assertion to `test_db.py` that reads
`information_schema.columns` and expects exactly `key`, `encrypted_value`, and
`updated_at` with text/text/timestamp types.

- [ ] **Step 2: Run the new tests and verify the expected failure**

Run:

```powershell
Set-Location apps/sync-service
pytest tests/test_sqlite_fallback.py -k app_setting -v
pytest tests/test_db.py -k app_settings -v
```

Expected: SQLite fails because `repo.upsert_app_setting` does not exist; the
PostgreSQL test fails on a configured test database because the table does not
exist, or skips under the repository's existing `TEST_DATABASE_URL` rule.

- [ ] **Step 3: Add the schema and repository implementation**

Append this table to both `SCHEMA_SQL` and `SQLITE_SCHEMA_SQL` in `db.py`:

```sql
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    encrypted_value TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

Add these functions to `repository.py`; keep the explicit timestamp so tests
and both database engines behave identically:

```python
def get_app_setting(conn: psycopg.Connection, key: str) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT key, encrypted_value, updated_at FROM app_settings WHERE key = %s",
            (key,),
        )
        return cur.fetchone()


def upsert_app_setting(
    conn: psycopg.Connection,
    *,
    key: str,
    encrypted_value: str,
    updated_at: datetime.datetime,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO app_settings (key, encrypted_value, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (key) DO UPDATE SET
                encrypted_value = EXCLUDED.encrypted_value,
                updated_at = EXCLUDED.updated_at
            """,
            (key, encrypted_value, updated_at),
        )


def delete_app_setting(conn: psycopg.Connection, key: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM app_settings WHERE key = %s", (key,))
```

- [ ] **Step 4: Run focused and repository regression tests**

Run:

```powershell
Set-Location apps/sync-service
pytest tests/test_sqlite_fallback.py tests/test_repository.py -v
pytest tests/test_db.py -v
```

Expected: all SQLite/repository tests pass; PostgreSQL tests pass when
`TEST_DATABASE_URL` is configured and otherwise retain their existing skips.

- [ ] **Step 5: Commit the schema slice**

```powershell
git add apps/sync-service/app/db.py apps/sync-service/app/repository.py apps/sync-service/tests/test_db.py apps/sync-service/tests/test_sqlite_fallback.py apps/sync-service/tests/test_repository.py
git commit -m "feat: add encrypted application settings storage"
```

### Task 2: Implement the injectable DPAPI credential service

**Files:**
- Create: `apps/sync-service/app/credential_protection.py`
- Create: `apps/sync-service/app/credentials.py`
- Create: `apps/sync-service/tests/test_credential_protection.py`
- Create: `apps/sync-service/tests/test_credentials.py`

**Interfaces:**
- Produces `CredentialProtectionError(RuntimeError)` and `CredentialValidationError(ValueError)`.
- Produces protocol `CredentialProtector.protect(plaintext: str) -> str` and `CredentialProtector.unprotect(protected_value: str) -> str`.
- Produces `DpapiCredentialProtector` using `CryptProtectData`/`CryptUnprotectData` with `CRYPTPROTECT_UI_FORBIDDEN`.
- Produces `AzureDevOpsCredentialStatus(configured: bool, updated_at: datetime.datetime | None)`.
- Produces `get_status(conn)`, `save_api_key(conn, protector, api_key, *, now_factory=...)`, `delete_api_key(conn)`, and `load_api_key(conn, protector)`.

- [ ] **Step 1: Write failing credential-service tests with a deterministic protector**

Create `test_credentials.py` with a real SQLite connection and this test
double:

```python
class PrefixProtector:
    def protect(self, plaintext: str) -> str:
        return f"protected:{plaintext}"

    def unprotect(self, protected_value: str) -> str:
        prefix = "protected:"
        if not protected_value.startswith(prefix):
            raise CredentialProtectionError("stored credential cannot be decrypted")
        return protected_value[len(prefix):]


def test_save_load_status_replace_and_delete_api_key(tmp_path):
    conn = db.SQLiteConnection(str(tmp_path / "credentials.sqlite3"))
    db.init_schema(conn)
    protector = PrefixProtector()
    saved_at = datetime.datetime(2026, 8, 18, 12, 0)

    assert credentials.get_status(conn) == credentials.AzureDevOpsCredentialStatus(False, None)
    credentials.save_api_key(
        conn, protector, "first-secret", now_factory=lambda: saved_at
    )
    conn.commit()

    assert credentials.load_api_key(conn, protector) == "first-secret"
    assert credentials.get_status(conn) == credentials.AzureDevOpsCredentialStatus(True, saved_at)
    assert repo.get_app_setting(conn, credentials.SETTING_KEY)["encrypted_value"] == "protected:first-secret"

    credentials.delete_api_key(conn)
    conn.commit()
    assert credentials.load_api_key(conn, protector) is None
    conn.close()
```

Add parameterized tests proving `""`, whitespace-only text, non-string input,
and a 4,097-character value raise `CredentialValidationError` before
`protector.protect` is called.

- [ ] **Step 2: Run the credential tests and verify the expected import failure**

Run:

```powershell
Set-Location apps/sync-service
pytest tests/test_credentials.py -v
```

Expected: collection fails because `app.credentials` and
`app.credential_protection` do not exist.

- [ ] **Step 3: Implement the credential service**

Create `credentials.py` with these stable names and transaction-agnostic
behavior:

```python
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
    if not isinstance(api_key, str) or not api_key.strip() or len(api_key) > MAX_API_KEY_LENGTH:
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
```

Do not call `commit` or `rollback` in this module; routes remain transaction
owners.

- [ ] **Step 4: Write failing protection tests before implementing DPAPI**

Create `test_credential_protection.py` with one platform-neutral invalid-Base64
test and a Windows-only round trip:

```python
@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI only")
def test_dpapi_round_trip_is_not_plaintext():
    protector = DpapiCredentialProtector()
    encrypted = protector.protect("secret-value")
    assert encrypted != "secret-value"
    assert b"secret-value" not in base64.b64decode(encrypted)
    assert protector.unprotect(encrypted) == "secret-value"


def test_unprotect_rejects_invalid_base64():
    with pytest.raises(CredentialProtectionError, match="cannot be decrypted"):
        DpapiCredentialProtector().unprotect("not-base64!!")
```

Run `pytest tests/test_credential_protection.py -v` and confirm failure because
`DpapiCredentialProtector` is missing.

- [ ] **Step 5: Implement the DPAPI adapter with explicit memory release**

Create `credential_protection.py` around this API. Keep the Win32 calls behind
private methods so importing the module on non-Windows remains possible:

```python
import base64
import ctypes
from ctypes import wintypes
from typing import Protocol

CRYPTPROTECT_UI_FORBIDDEN = 0x1


class CredentialProtectionError(RuntimeError):
    pass


class CredentialProtector(Protocol):
    def protect(self, plaintext: str) -> str: ...
    def unprotect(self, protected_value: str) -> str: ...


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]
```

`DpapiCredentialProtector.protect` must UTF-8 encode the input, call
`CryptProtectData`, copy `out_blob` with `ctypes.string_at`, call
`LocalFree(out_blob.pbData)` in `finally`, and Base64-encode the copy.
`unprotect` must validate Base64 with `base64.b64decode(value, validate=True)`,
call `CryptUnprotectData`, UTF-8 decode the copied result, and free the returned
buffer in `finally`. On a false Win32 return value or decoding failure, raise
only `CredentialProtectionError("stored credential cannot be decrypted")`;
do not include input or ciphertext in the exception.

- [ ] **Step 6: Run the complete credential unit slice**

Run:

```powershell
Set-Location apps/sync-service
pytest tests/test_credentials.py tests/test_credential_protection.py -v
```

Expected: deterministic service tests pass everywhere; the real DPAPI round
trip passes on Windows and skips elsewhere.

- [ ] **Step 7: Commit the credential-service slice**

```powershell
git add apps/sync-service/app/credential_protection.py apps/sync-service/app/credentials.py apps/sync-service/tests/test_credential_protection.py apps/sync-service/tests/test_credentials.py
git commit -m "feat: protect Azure DevOps credential with DPAPI"
```

### Task 3: Expose the sync-service credential API and use the stored PAT

**Files:**
- Modify: `apps/sync-service/app/ado_client.py:1-135`
- Modify: `apps/sync-service/app/routes.py:1-234`
- Modify: `apps/sync-service/app/scheduler.py:1-38`
- Modify: `apps/sync-service/app/config.py:1-26`
- Modify: `apps/sync-service/run.py`
- Modify: `apps/sync-service/tests/test_ado_client.py`
- Modify: `apps/sync-service/tests/test_routes.py`
- Modify: `apps/sync-service/tests/test_sync_service.py`
- Create: `apps/sync-service/tests/test_scheduler.py`

**Interfaces:**
- `AdoClient(organization, project, pat: str | None = None, *, pat_provider: Callable[[], str | None] | None = None)` no longer reads configuration and preserves positional-PAT compatibility.
- `create_app(conn_factory=db.get_connection, credential_protector=None)` remains backward compatible.
- `build_scheduler(conn_factory=db.get_connection, credential_protector=None)` uses the same protector interface.
- Produces sync-service GET/PUT/DELETE `/api/settings/azure-devops`.
- `start_manual_sync` and `_run_manual_sync_worker` receive the injected protector and create a lazy credential-backed client.

- [ ] **Step 1: Write failing AdoClient tests for lazy credential resolution**

Add tests to `test_ado_client.py`:

```python
def test_auth_resolves_and_caches_pat_from_provider():
    provider = MagicMock(return_value="stored-pat")
    client = AdoClient("org", "project", pat_provider=provider)
    assert client._auth() == ("", "stored-pat")
    assert client._auth() == ("", "stored-pat")
    provider.assert_called_once_with()


def test_auth_reports_missing_credential_without_reading_environment():
    client = AdoClient("org", "project", pat_provider=lambda: None)
    with pytest.raises(AdoAuthError, match="not configured"):
        client._auth()


def test_auth_wraps_protection_failure_without_secret_material():
    def fail():
        raise CredentialProtectionError("stored credential cannot be decrypted")

    with pytest.raises(AdoAuthError, match="cannot be decrypted") as error:
        AdoClient("org", "project", pat_provider=fail)._auth()
    assert "api_key" not in str(error.value).lower()
```

Run `pytest tests/test_ado_client.py -k "provider or credential" -v` and verify
failure because `pat_provider` is not accepted.

- [ ] **Step 2: Implement lazy, explicit credential resolution**

Remove the import and call to `get_ado_api_key`. Add a private unresolved
sentinel and this behavior:

```python
from collections.abc import Callable
from app.credential_protection import CredentialProtectionError

_UNRESOLVED = object()


class AdoClient:
    def __init__(
        self,
        organization: str,
        project: str,
        pat: str | None = None,
        *,
        pat_provider: Callable[[], str | None] | None = None,
    ):
        self.organization = organization
        self.project = project
        self._pat = pat if pat is not None else _UNRESOLVED
        self._pat_provider = pat_provider

    def _auth(self):
        if self._pat is _UNRESOLVED:
            try:
                self._pat = self._pat_provider() if self._pat_provider else None
            except CredentialProtectionError as exc:
                raise AdoAuthError("Stored Azure DevOps credential cannot be decrypted") from exc
        if not self._pat:
            raise AdoAuthError("Azure DevOps credential is not configured")
        return ("", self._pat)
```

Keep explicit `pat="test-pat"` compatibility for existing client tests.

- [ ] **Step 3: Write failing sync-service credential-route tests**

Add a `PrefixProtector` fixture and call `create_app` with
`credential_protector=protector`. Test:

```python
def test_api_credential_lifecycle_never_returns_secret(client):
    assert client.get("/api/settings/azure-devops").get_json() == {
        "configured": False,
        "updated_at": None,
    }

    saved = client.put(
        "/api/settings/azure-devops", json={"api_key": "browser-secret"}
    )
    assert saved.status_code == 200
    assert saved.get_json()["configured"] is True
    assert "browser-secret" not in saved.get_data(as_text=True)

    loaded = client.get("/api/settings/azure-devops")
    assert loaded.get_json()["configured"] is True
    assert "browser-secret" not in loaded.get_data(as_text=True)

    removed = client.delete("/api/settings/azure-devops")
    assert removed.status_code == 204
    assert client.get("/api/settings/azure-devops").get_json() == {
        "configured": False,
        "updated_at": None,
    }
```

Add parameterized PUT cases for no JSON, no `api_key`, empty, whitespace,
non-string, and 4,097 characters; each must return
`400 {"error": "invalid Azure DevOps credential"}` without echoing the input.
Add a protector that raises `CredentialProtectionError` and assert PUT returns
`500 {"error": "credential could not be stored"}`, rolls back, and omits the
submitted PAT and exception details.

Run `pytest tests/test_routes.py -k credential -v` and confirm 404 failures.

- [ ] **Step 4: Implement the credential routes and serializers**

Inside `create_app`, choose
`credential_protector or DpapiCredentialProtector()`. Add a serializer:

```python
def _serialize_credential_status(status):
    return {
        "configured": status.configured,
        "updated_at": status.updated_at.isoformat() if status.updated_at else None,
    }
```

Implement GET with `credentials.get_status`, PUT with strict dict/string
validation plus `credentials.save_api_key`, and DELETE with
`credentials.delete_api_key`. PUT and DELETE commit only after success;
protection failure returns a generic 500 JSON error after rollback and never
includes exception input.

- [ ] **Step 5: Write failing manual and scheduled sync tests**

Update route-worker assertions so the fake `AdoClient` receives a
`pat_provider`. Capture and invoke that provider against the worker connection,
then assert it returns the saved plaintext through the injected fake protector.

Create `tests/test_scheduler.py` with a due active area, saved ciphertext, and
patched `AdoClient`; invoke
`_sync_all_active(conn_factory, protector)` and assert the provider resolves
the same PAT. Add a missing-credential integration test where a real
`AdoClient` reaches `_auth` during `run_sync` and the area finishes with
`last_sync_status == "auth_error"`.

Run:

```powershell
pytest tests/test_routes.py -k "worker and credential" -v
pytest tests/test_scheduler.py -v
pytest tests/test_sync_service.py -k "credential or auth_error" -v
```

Expected: failures show the worker/scheduler still instantiate `AdoClient`
without the stored credential provider.

- [ ] **Step 6: Wire the provider through routes, scheduler, and run.py**

Use this exact client construction in both manual and scheduled paths:

```python
client = AdoClient(
    row["organization"],
    row["project"],
    pat_provider=lambda: credentials.load_api_key(conn, credential_protector),
)
```

Change signatures consistently:

```python
def start_manual_sync(conn_factory, area_path_id: int, credential_protector) -> bool: ...
def _run_manual_sync_worker(conn_factory, area_path_id: int, credential_protector) -> None: ...
def _sync_all_active(conn_factory, credential_protector) -> None: ...
def build_scheduler(conn_factory=db.get_connection, credential_protector=None) -> BackgroundScheduler: ...
```

In `run.py`, create one `DpapiCredentialProtector` and pass it to both
`create_app` and `build_scheduler`. Remove `get_ado_api_key` from `config.py`.
Do not catch `AdoAuthError` outside `run_sync`.

- [ ] **Step 7: Run backend credential and sync regressions**

Run:

```powershell
Set-Location apps/sync-service
pytest tests/test_credential_protection.py tests/test_credentials.py tests/test_ado_client.py tests/test_routes.py tests/test_scheduler.py tests/test_sync_service.py -v
```

Expected: credential API, manual sync, scheduled sync, rollback, and status
tests pass; no test depends on `AZURE_DEVOPS_API_KEY` in `.env`.

- [ ] **Step 8: Commit the sync-service integration**

```powershell
git add apps/sync-service/app/ado_client.py apps/sync-service/app/routes.py apps/sync-service/app/scheduler.py apps/sync-service/app/config.py apps/sync-service/run.py apps/sync-service/tests/test_ado_client.py apps/sync-service/tests/test_routes.py apps/sync-service/tests/test_scheduler.py apps/sync-service/tests/test_sync_service.py
git commit -m "feat: manage Azure DevOps credential through sync service"
```

### Task 4: Proxy credential status and mutations through api-read

**Files:**
- Modify: `apps/api-read/app/routes.py:30-97`
- Modify: `apps/api-read/tests/test_routes.py`
- Verify: `apps/api-read/tests/test_readonly_guardrail.py`

**Interfaces:**
- Produces public GET/PUT/DELETE `/api/settings/azure-devops`.
- Uses existing `SyncServiceClient.request(method, path, json_body=None)`.
- Preserves upstream JSON and status, and maps transport failure to existing 503 behavior.

- [ ] **Step 1: Write failing proxy contract tests**

Extend the route parameterization with:

```python
(
    "GET",
    "/api/settings/azure-devops",
    None,
    200,
    {"configured": True, "updated_at": "2026-08-18T12:00:00"},
),
(
    "PUT",
    "/api/settings/azure-devops",
    {"api_key": "browser-secret"},
    200,
    {"configured": True, "updated_at": "2026-08-18T12:00:00"},
),
(
    "DELETE",
    "/api/settings/azure-devops",
    None,
    204,
    None,
),
```

Assert the recording client sees the full PUT input but the public response
does not contain `browser-secret`. Add a 503 test for GET using the existing
`UnavailableSyncServiceClient`.

- [ ] **Step 2: Run the proxy tests and verify 404 failures**

Run:

```powershell
Set-Location apps/api-read
pytest tests/test_routes.py -k azure_devops -v
```

Expected: all three public routes return 404.

- [ ] **Step 3: Add the three forwarding routes**

Use the existing `forward_to_sync_service` boundary:

```python
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
```

Do not open a database connection in these routes.

- [ ] **Step 4: Run API tests and the writer guardrail**

Run:

```powershell
Set-Location apps/api-read
pytest tests/test_routes.py tests/test_readonly_guardrail.py -v
```

Expected: proxy behavior and read-only guardrail pass.

- [ ] **Step 5: Commit the API facade slice**

```powershell
git add apps/api-read/app/routes.py apps/api-read/tests/test_routes.py
git commit -m "feat: proxy Azure DevOps credential settings"
```

### Task 5: Add the Astryx credential workflow to the synchronization page

**Files:**
- Modify: `apps/web-read/src/services/syncServiceClient.ts:1-98`
- Modify: `apps/web-read/src/services/syncServiceClient.test.ts`
- Create: `apps/web-read/src/components/AzureDevOpsCredentialCard.tsx`
- Create: `apps/web-read/src/components/AzureDevOpsCredentialCard.test.tsx`
- Modify: `apps/web-read/src/pages/SynchronizationPage.tsx:1-390`
- Modify: `apps/web-read/src/pages/SynchronizationPage.test.tsx`

**Interfaces:**
- Produces TypeScript type `AzureDevOpsCredentialStatus`.
- Produces client functions `fetchAzureDevOpsCredentialStatus`, `saveAzureDevOpsCredential`, and `deleteAzureDevOpsCredential`.
- Produces `AzureDevOpsCredentialCard` with controlled async behavior and no PAT echo after save.
- `SynchronizationPage` renders the credential card above area-path cards and refreshes credential status independently.

- [ ] **Step 1: Write failing web-client tests**

Add imports and tests to `syncServiceClient.test.ts`:

```typescript
test("loads Azure DevOps credential status without a secret", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    configured: true,
    updated_at: "2026-08-18T12:00:00",
  }), { status: 200, headers: { "Content-Type": "application/json" } })));

  await expect(fetchAzureDevOpsCredentialStatus()).resolves.toEqual({
    configured: true,
    updated_at: "2026-08-18T12:00:00",
  });
  expect(fetch).toHaveBeenCalledWith(
    "http://127.0.0.1:5001/api/settings/azure-devops"
  );
});

test("saves and deletes the Azure DevOps credential", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({
      configured: true,
      updated_at: "2026-08-18T12:00:00",
    }), { status: 200, headers: { "Content-Type": "application/json" } }))
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetchMock);

  await saveAzureDevOpsCredential("browser-secret");
  await deleteAzureDevOpsCredential();

  expect(fetchMock.mock.calls[0][1]).toMatchObject({
    method: "PUT",
    body: JSON.stringify({ api_key: "browser-secret" }),
  });
  expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: "DELETE" });
});
```

Run `npm test -- src/services/syncServiceClient.test.ts` and verify missing
exports fail the test.

- [ ] **Step 2: Implement the typed client methods**

Add:

```typescript
export interface AzureDevOpsCredentialStatus {
  configured: boolean;
  updated_at: string | null;
}

export function fetchAzureDevOpsCredentialStatus(): Promise<AzureDevOpsCredentialStatus> {
  return request<AzureDevOpsCredentialStatus>("/api/settings/azure-devops");
}

export function saveAzureDevOpsCredential(apiKey: string): Promise<AzureDevOpsCredentialStatus> {
  return request<AzureDevOpsCredentialStatus>("/api/settings/azure-devops", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export async function deleteAzureDevOpsCredential(): Promise<void> {
  await request<void>("/api/settings/azure-devops", { method: "DELETE" });
}
```

Keep response parsing centralized in the existing `request` function.

- [ ] **Step 3: Write failing Astryx component tests**

Mock the three new client functions and render inside the existing Astryx
`Theme`. Tests must prove:

```typescript
test("saves a PAT, clears the password field, and shows configured status", async () => {
  vi.mocked(fetchAzureDevOpsCredentialStatus).mockResolvedValue({
    configured: false,
    updated_at: null,
  });
  vi.mocked(saveAzureDevOpsCredential).mockResolvedValue({
    configured: true,
    updated_at: "2026-08-18T12:00:00",
  });
  renderCredentialCard();

  fireEvent.change(await screen.findByLabelText("Azure DevOps personal access token"), {
    target: { value: "browser-secret" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save credential" }));

  await waitFor(() => expect(saveAzureDevOpsCredential).toHaveBeenCalledWith("browser-secret"));
  expect(screen.getByLabelText("Azure DevOps personal access token")).toHaveValue("");
  expect(screen.getByText("Configured")).toBeInTheDocument();
  expect(screen.queryByDisplayValue("browser-secret")).not.toBeInTheDocument();
});
```

Add tests for initial status loading, 4,097-character save disabled, save
failure shown in an Astryx `Banner`, and confirmed removal calling DELETE.

Run `npm test -- src/components/AzureDevOpsCredentialCard.test.tsx` and verify
the missing module failure.

- [ ] **Step 4: Implement the credential card with Astryx only**

Use existing imports from `@astryxdesign/core`:

```tsx
<Card padding={3}>
  <VStack gap={3}>
    <HStack justify="between" align="center" wrap="wrap">
      <Text as="h2" type="large" weight="semibold">Azure DevOps credential</Text>
      <Badge
        variant={status?.configured ? "success" : "warning"}
        label={status?.configured ? "Configured" : "Not configured"}
      />
    </HStack>
    <TextInput
      type="password"
      label="Azure DevOps personal access token"
      description="The token is encrypted for your Windows user and is never shown again."
      value={apiKey}
      onChange={setApiKey}
      isRequired
    />
    <HStack gap={2} justify="end">
      <Button
        label="Remove credential"
        variant="destructive"
        isDisabled={!status?.configured}
        onClick={() => setConfirmRemove(true)}
      />
      <Button
        label="Save credential"
        variant="primary"
        isLoading={isSaving}
        isDisabled={!apiKey.trim() || apiKey.length > 4096}
        onClick={() => void handleSave()}
      />
    </HStack>
  </VStack>
</Card>
```

Use Astryx `AlertDialog` for removal and `Banner` for errors/success. On every
successful save set `apiKey` to `""` before rendering success. Never store the
submitted value in the status object or success text.

- [ ] **Step 5: Integrate the card and update auth-error guidance**

Render `<AzureDevOpsCredentialCard />` near the top of
`SynchronizationPage`, before the area-path grid. Replace the current
`AZURE_DEVOPS_API_KEY` copy with:

```tsx
description={
  areaPath.last_error_msg
    ?? "Update the Azure DevOps credential on this page and try again."
}
```

Update the page mock factory to include the new client exports so existing
polling tests remain isolated.

- [ ] **Step 6: Run the web tests and production build**

Run:

```powershell
Set-Location apps/web-read
npm test -- src/services/syncServiceClient.test.ts src/components/AzureDevOpsCredentialCard.test.tsx src/pages/SynchronizationPage.test.tsx
npm run build
```

Expected: focused tests pass, TypeScript accepts `TextInput type="password"`,
and the build adds no CSS file owned by this feature.

- [ ] **Step 7: Commit the Astryx credential workflow**

```powershell
git add apps/web-read/src/services/syncServiceClient.ts apps/web-read/src/services/syncServiceClient.test.ts apps/web-read/src/components/AzureDevOpsCredentialCard.tsx apps/web-read/src/components/AzureDevOpsCredentialCard.test.tsx apps/web-read/src/pages/SynchronizationPage.tsx apps/web-read/src/pages/SynchronizationPage.test.tsx
git commit -m "feat: configure Azure DevOps credential in web"
```

### Task 6: Remove `.env` credential guidance and verify the complete feature

**Files:**
- Modify: `apps/sync-service/README.md`
- Modify: `README.md`
- Modify: `apps/sync-service/app/templates/index.html`
- Modify: `apps/sync-service/tests/test_routes.py`
- Verify: all files changed by Tasks 1-5

**Interfaces:**
- Documentation identifies the synchronization page as the only PAT configuration path.
- The legacy sync-service HTML banner no longer refers to `.env` or `AZURE_DEVOPS_API_KEY`.
- No production code exposes `get_ado_api_key`.

- [ ] **Step 1: Write the failing legacy-copy assertion**

Change `test_index_shows_auth_error_banner` to assert the rendered HTML
contains `Configure the Azure DevOps credential in the Synchronization page`
and does not contain `AZURE_DEVOPS_API_KEY`.

Run `pytest tests/test_routes.py::test_index_shows_auth_error_banner -v` and
verify it fails on the old template copy.

- [ ] **Step 2: Update user and developer documentation**

Replace every PAT setup instruction with this flow:

```text
Open the web application, select Synchronization, enter the Azure DevOps
personal access token in Azure DevOps credential, and choose Save credential.
The token is encrypted for the current Windows user and is not stored in .env.
```

Keep `DATABASE_URL`, `TEST_DATABASE_URL`, and other non-secret runtime options
documented. Update the legacy HTML banner to point to the web page without
adding a credential form to the legacy screen.

- [ ] **Step 3: Run secret-reference and write-path guardrails**

Run:

```powershell
rg -n "AZURE_DEVOPS_API_KEY|get_ado_api_key" README.md apps/sync-service/app apps/sync-service/README.md apps/api-read/app apps/api-read/README.md apps/web-read/src apps/web-read/README.md -g "!**/node_modules/**" -g "!**/dist/**"
rg -n "INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE" apps/api-read/app
```

Expected: the first command returns no matches in production code and user
documentation; the second shows no newly introduced write SQL. Negative
security assertions may still use the removed environment-variable name in
test files.

- [ ] **Step 4: Run complete application suites**

Run:

```powershell
Set-Location apps/sync-service
pytest -v
Set-Location ../api-read
pytest -v
Set-Location ../web-read
npm test
npm run build
```

Expected: all configured tests pass. Record PostgreSQL tests skipped solely
because `TEST_DATABASE_URL` is absent separately from failures.

- [ ] **Step 5: Inspect the final feature diff**

Run:

```powershell
Set-Location ../..
git diff --check
git status --short
git log --oneline -6
```

Confirm only credential-feature files changed, every write query is in
`repository.py`, no PAT appears in test output, and the portable-distribution
plan can consume GET/PUT/DELETE `/api/settings/azure-devops` unchanged.

- [ ] **Step 6: Commit the documentation and legacy-copy update**

```powershell
git add README.md apps/sync-service/README.md apps/sync-service/app/templates/index.html apps/sync-service/tests/test_routes.py
git commit -m "docs: move PAT setup to synchronization page"
```
