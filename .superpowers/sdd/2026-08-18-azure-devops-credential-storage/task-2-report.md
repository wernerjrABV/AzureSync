## Task 2 report — injectable DPAPI credential service

### Scope completed

- Added `apps/sync-service/app/credentials.py` with:
  - `CredentialValidationError`
  - `AzureDevOpsCredentialStatus`
  - `get_status(conn)`
  - `save_api_key(conn, protector, api_key, *, now_factory=...)`
  - `delete_api_key(conn)`
  - `load_api_key(conn, protector)`
- Added `apps/sync-service/app/credential_protection.py` with:
  - `CredentialProtectionError`
  - `CredentialProtector` protocol
  - `DpapiCredentialProtector` implemented with Windows DPAPI
  - explicit `LocalFree(...)` cleanup of Win32-owned buffers
- Added new tests:
  - `apps/sync-service/tests/test_credentials.py`
  - `apps/sync-service/tests/test_credential_protection.py`
- Preserved the repository app-setting boundary from Task 1 as strict canonical
  Base64 storage, while moving the deterministic non-Windows seam into the fake
  protector used by Task 2 tests. The fake protector now wraps deterministic
  plaintext markers inside Base64 so the repository invariant remains intact.
- The repository boundary continues to enforce:
  - allowed key exactly `azure_devops_api_key`
  - maximum protected value length of 4096
  - non-empty canonical Base64 protected values
- Updated existing repository/storage tests to prove non-Base64 values still
  reject at the storage boundary.

### TDD evidence

#### RED

Command:

```powershell
pytest tests/test_credentials.py -v
```

Result:

- Collection failed as expected before implementation with:
  - `ModuleNotFoundError: No module named 'app.credential_protection'`

This verified the credential-service slice was missing before production code
was added.

#### GREEN

Command:

```powershell
pytest tests/test_credentials.py -v
```

Result:

- `5 passed`

Command:

```powershell
pytest tests/test_credential_protection.py -v
```

Result:

- `2 passed`
- On this Windows environment, the DPAPI round-trip test executed instead of
  skipping.

### Verification before completion

Command:

```powershell
pytest tests/test_credentials.py tests/test_credential_protection.py -v
```

Result:

- `7 passed`

Additional regression coverage for the preserved strict Base64 storage
boundary:

```powershell
pytest tests/test_sqlite_fallback.py -k app_setting -v
pytest tests/test_repository.py -k app_setting -v
```

Results:

- SQLite fallback slice: `5 passed, 3 deselected`
- PostgreSQL-gated repository slice: `7 skipped, 21 deselected`

The PostgreSQL-backed tests remain skipped in this environment because
`TEST_DATABASE_URL` is not configured, which preserves the existing baseline
skip behavior rather than introducing a new failure.

### Reviewer follow-up fix

Reviewer issue:

- My first Task 2 implementation weakened the repository invariant by allowing
  opaque non-Base64 protected values such as `cipher-one`, which conflicted with
  the strict DPAPI/Base64 storage boundary established in Task 1.

Test-first correction:

- Updated `tests/test_credentials.py` so the deterministic fake protector now
  returns Base64-encoded deterministic ciphertext while keeping the opaque
  `"protected:..."` marker inside the protector implementation.
- Restored the repository/storage tests to require strict Base64 rejection for
  empty and non-Base64 ciphertext:
  - `tests/test_sqlite_fallback.py::test_sqlite_app_setting_rejects_empty_ciphertext`
  - `tests/test_sqlite_fallback.py::test_sqlite_app_setting_rejects_non_base64_ciphertext`
  - `tests/test_repository.py::test_app_setting_rejects_empty_ciphertext`
  - `tests/test_repository.py::test_app_setting_rejects_non_base64_ciphertext`

RED command:

```powershell
pytest tests/test_sqlite_fallback.py -k app_setting -v
```

RED result:

- `test_sqlite_app_setting_rejects_empty_ciphertext` failed because
  `repository.py` still raised the weakened message
  `app setting encrypted_value must be non-empty`
- `test_sqlite_app_setting_rejects_non_base64_ciphertext` failed because
  `repository.py` still accepted `cipher-one`

Implementation fix:

- Restored strict canonical Base64 validation in `app/repository.py` using
  `base64.b64decode(..., validate=True)` plus canonical re-encoding checks.
- Restored the original repository validation error message:
  - `ValueError("app setting encrypted_value must be non-empty Base64")`

GREEN verification:

```powershell
pytest tests/test_credentials.py -v
pytest tests/test_sqlite_fallback.py -k app_setting -v
pytest tests/test_repository.py -k app_setting -v
pytest tests/test_credentials.py tests/test_credential_protection.py -v
```

Results:

- credential service slice: `5 passed`
- SQLite app-setting regression slice: `5 passed, 3 deselected`
- PostgreSQL-gated repository slice: `7 skipped, 21 deselected`
- final credential verification slice: `7 passed`

### Notes

- `credentials.py` remains transaction-boundary agnostic: it does not call
  `commit()` or `rollback()`.
- `credential_protection.py` keeps Win32 calls behind private helper methods so
  the module remains importable on non-Windows systems.
- Decryption failures intentionally raise only
  `CredentialProtectionError("stored credential cannot be decrypted")` without
  echoing plaintext or ciphertext.
- The focused pytest runs emit an existing Python 3.12+ sqlite datetime adapter
  deprecation warning from `app/db.py`; I did not change that baseline in Task 2.
