## Task 2 report — Windows launcher control primitives

### Scope completed

- Added immutable `AppPaths` discovery for installation, service executables,
  per-user data, logs, run state, database, and stop request paths.
- Added deterministic per-user `InstanceNames` based on a short SHA-256 suffix
  of the resolved data root, without embedding usernames or paths.
- Added Win32 `ctypes` primitives: `NamedMutex`, `NamedEvent`,
  `KillOnCloseJob`, and `show_error`.
- Added Windows integration and path/unit tests. Kernel integration tests are
  marked Windows-only and skip on other platforms.

### Verification

```powershell
pytest apps/launcher/tests/test_paths.py apps/launcher/tests/test_windows_control.py -v
```

Result: `7 passed` on Windows. The non-frozen fallback regression confirms the
default executable resolves to the repository/install root rather than its
`apps` parent.

### Reviewer follow-up

Corrected `AppPaths.discover()` from `Path(__file__).resolve().parents[2]` to
`parents[3]`, which is the repository/install root for
`apps/launcher/azuresync_launcher/paths.py`, and added explicit regression
coverage.
