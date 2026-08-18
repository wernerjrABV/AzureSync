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
- Adjusted the repository app-setting boundary so it accepts opaque protected
  values instead of requiring Base64, which is necessary for the deterministic
  non-Windows test seam from this task while still preserving:
  - allowed key exactly `azure_devops_api_key`
  - maximum protected value length of 4096
  - non-empty protected values
- Updated existing repository/storage tests to match the opaque-ciphertext
  boundary.

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

Additional regression coverage for the widened opaque-ciphertext storage
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
