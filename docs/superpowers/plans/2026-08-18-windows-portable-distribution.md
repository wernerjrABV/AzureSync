# Windows Portable Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a self-contained Windows x64 ZIP that starts AzureSync at `http://127.0.0.1:5173` without Python, Node.js, npm, or a source checkout on the target machine.

**Architecture:** A windowless `AzureSync.exe` supervises separately frozen `sync-service.exe` and `api-read.exe` processes, owns them through a Windows Job Object, waits for health, and opens the browser. `api-read` serves the production React build and public APIs on port 5173; all mutable data lives under `%LOCALAPPDATA%\AzureSync`, and `StopAzureSync.exe` signals the same per-user launcher instance.

**Tech Stack:** Windows x64, Python 3.12+, Node.js 22+, PyInstaller 6.21.0, Waitress 3.0.2, PowerShell 5.1+, Flask 3.1, React 19, Vite 6, SQLite, pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-08-18-windows-portable-distribution-and-credential-design.md`

## Global Constraints

- Complete `docs/superpowers/plans/2026-08-18-azure-devops-credential-storage.md` first; this plan consumes its credential routes unchanged.
- The distributed platform is Windows x64 only; the build itself must run on Windows x64 because PyInstaller is not a cross-compiler.
- The build machine requires Python x64 3.12 or newer and Node.js x64 22 or newer; the target machine requires neither.
- The public URL is fixed at `http://127.0.0.1:5173`; the internal sync service is fixed at `http://127.0.0.1:5000`.
- Portable data is fixed at `%LOCALAPPDATA%\AzureSync\data\azure_sync.sqlite3`; logs and run state use sibling `logs` and `run` directories.
- The launcher waits up to 30 seconds for health, polling every 250 ms, and waits up to 30 seconds for graceful shutdown.
- The package must never read an adjacent `.env` in portable mode and must force an empty `DATABASE_URL` plus an explicit SQLite path.
- `sync-service` remains the only database writer; `api-read` remains free of write SQL even while serving the SPA.
- The frontend uses relative API URLs in production and existing port-5001 defaults in Vite development.
- No process argument, environment value, log, or artifact contains the Azure DevOps PAT.
- Keep `AzureSync.exe` and `StopAzureSync.exe` as the only user-facing files; internal service layouts are implementation details.
- Follow TDD for Python/TypeScript runtime behavior. Generated ZIP/hash outputs are verified by smoke tests and are not committed.
- Pin PyInstaller to `6.21.0` and Waitress to `3.0.2`; review pins under the repository's technology lifecycle policy before future releases.

---

### Task 1: Add portable configuration precedence and same-origin SPA serving

**Files:**
- Modify: `apps/sync-service/app/config.py:1-26`
- Create: `apps/sync-service/tests/test_config.py`
- Modify: `apps/api-read/app/config.py:1-36`
- Modify: `apps/api-read/app/routes.py:1-174`
- Modify: `apps/api-read/tests/test_routes.py`
- Create: `apps/api-read/tests/test_config.py`
- Create: `apps/web-read/src/services/apiBaseUrl.ts`
- Create: `apps/web-read/src/services/apiBaseUrl.test.ts`
- Modify: `apps/web-read/src/services/apiReadClient.ts:1-90`
- Modify: `apps/web-read/src/services/syncServiceClient.ts:1-125`

**Interfaces:**
- Produces config helper behavior: an explicitly present OS environment value, including `""`, wins over `.env`.
- Produces `get_web_dist_path() -> str | None` in api-read config.
- Extends `create_app(..., web_dist_path: str | Path | None = None)` without breaking existing injected tests.
- Produces `API_BASE_URL`, equal to explicit `VITE_API_READ_BASE_URL`, otherwise `http://127.0.0.1:5001` in development and `""` in production.

- [ ] **Step 1: Write failing environment-precedence tests**

Create `apps/api-read/tests/test_config.py` and
`apps/sync-service/tests/test_config.py` with equivalent focused tests:

```python
def test_environment_values_override_dotenv_even_when_empty(monkeypatch):
    monkeypatch.setattr(config, "_ENV", {
        "DATABASE_URL": "postgresql://from-file",
        "SQLITE_DATABASE_PATH": "from-file.sqlite3",
    })
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("SQLITE_DATABASE_PATH", r"C:\portable\azure_sync.sqlite3")

    assert config.get_database_url() == ""
    assert config.get_sqlite_database_path() == r"C:\portable\azure_sync.sqlite3"
```

For api-read, also assert `API_READ_PORT=5173`,
`SYNC_SERVICE_BASE_URL=http://127.0.0.1:5000`, and
`AZURESYNC_WEB_DIST_PATH=C:\bundle\web` are returned exactly.

Run both focused config files. Expected: values still come from `_ENV` because
the current modules do not inspect `os.environ`.

- [ ] **Step 2: Implement a shared per-module `_get_value` rule**

In each config module, add:

```python
import os


def _get_value(name: str, default: str = "") -> str:
    if name in os.environ:
        return os.environ[name]
    return _ENV.get(name, default) or default
```

Route every existing getter through `_get_value`. In api-read add:

```python
def get_web_dist_path() -> str | None:
    value = _get_value("AZURESYNC_WEB_DIST_PATH")
    return value or None
```

An empty `DATABASE_URL` must remain empty; do not use `os.environ.get(...) or
_ENV[...]`.

- [ ] **Step 3: Write failing SPA-serving tests**

Add tests that create a temporary `index.html` and `assets/app.js`:

```python
def test_serves_production_spa_and_preserves_api_routes(tmp_path, db_conn):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<main>AzureSync portable</main>", encoding="utf-8")
    (web / "assets" / "app.js").write_text("window.portable = true", encoding="utf-8")
    app = create_app(conn_factory=lambda: db_conn, web_dist_path=web)

    with app.test_client() as client:
        assert b"AzureSync portable" in client.get("/").data
        assert b"AzureSync portable" in client.get("/synchronization").data
        assert b"window.portable" in client.get("/assets/app.js").data
        assert client.get("/health").get_json() == {"status": "ok"}
        assert client.get("/api/not-a-route").status_code == 404
```

Also test a nonexistent configured directory fails app creation with a message
that includes the directory path but no environment dump.

Run `pytest tests/test_routes.py -k "production_spa or web_dist" -v` and
verify `create_app` rejects the new keyword.

- [ ] **Step 4: Implement static assets and SPA fallback**

Create Flask with `static_folder=None`. Resolve `web_dist_path` from the
argument first and `get_web_dist_path()` second. Register the fallback only
when a path is configured:

```python
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_web(path: str):
    if path.startswith("api/"):
        return jsonify({"error": "not found"}), 404
    if path and (web_root / path).is_file():
        return send_from_directory(web_root, path)
    return send_from_directory(web_root, "index.html")
```

Register this after concrete API routes. Use `Path.resolve()` for the root and
`send_from_directory` for containment; never concatenate untrusted paths into
an open call.

- [ ] **Step 5: Write and implement frontend base-URL tests**

Create `apiBaseUrl.ts`:

```typescript
export const API_BASE_URL = import.meta.env.VITE_API_READ_BASE_URL
  ?? (import.meta.env.DEV ? "http://127.0.0.1:5001" : "");
```

Write `apiBaseUrl.test.ts` asserting the Vitest development value is the
existing port-5001 URL. Import `API_BASE_URL` from both clients and remove
their duplicated constants. The production build verification in Task 6 will
inspect built JavaScript and confirm no hard-coded port 5001 remains.

- [ ] **Step 6: Run focused backend/frontend verification**

Run:

```powershell
Set-Location apps/api-read
pytest tests/test_config.py tests/test_routes.py -v
Set-Location ../sync-service
pytest tests/test_config.py -v
Set-Location ../web-read
npm test -- src/services/apiBaseUrl.test.ts src/services/apiReadClient.test.ts src/services/syncServiceClient.test.ts
npm run build
```

Expected: environment precedence, API routes, SPA fallback, and both client
suites pass.

- [ ] **Step 7: Commit runtime configuration and static serving**

```powershell
git add apps/sync-service/app/config.py apps/sync-service/tests/test_config.py apps/api-read/app/config.py apps/api-read/app/routes.py apps/api-read/tests/test_config.py apps/api-read/tests/test_routes.py apps/web-read/src/services/apiBaseUrl.ts apps/web-read/src/services/apiBaseUrl.test.ts apps/web-read/src/services/apiReadClient.ts apps/web-read/src/services/syncServiceClient.ts
git commit -m "feat: serve portable web app from api read"
```

### Task 2: Implement Windows per-user control and process-ownership primitives

**Files:**
- Create: `apps/launcher/azuresync_launcher/__init__.py`
- Create: `apps/launcher/azuresync_launcher/paths.py`
- Create: `apps/launcher/azuresync_launcher/windows_control.py`
- Create: `apps/launcher/tests/test_paths.py`
- Create: `apps/launcher/tests/test_windows_control.py`

**Interfaces:**
- Produces immutable `AppPaths.discover(executable=None, local_app_data=None) -> AppPaths`.
- Produces deterministic `InstanceNames.for_data_root(data_root) -> InstanceNames`.
- Produces `NamedMutex.acquire(name) -> tuple[NamedMutex, bool]`.
- Produces `NamedEvent.create(name)`, `NamedEvent.open(name)`, `.set()`, `.wait(timeout_ms)`, and `.close()`.
- Produces `KillOnCloseJob.create()`, `.assign(process_handle)`, and `.close()`.
- Produces `show_error(title: str, message: str) -> None` using `MessageBoxW`.

- [ ] **Step 1: Write failing AppPaths tests**

Create tests with explicit paths rather than real `%LOCALAPPDATA%`:

```python
def test_discovers_install_services_and_mutable_paths(tmp_path):
    install = tmp_path / "AzureSync-win-x64"
    executable = install / "AzureSync.exe"
    local = tmp_path / "LocalAppData"

    paths = AppPaths.discover(executable=executable, local_app_data=local)

    assert paths.install_dir == install
    assert paths.sync_executable == install / "_services" / "sync-service" / "sync-service.exe"
    assert paths.api_executable == install / "_services" / "api-read" / "api-read.exe"
    assert paths.data_dir == local / "AzureSync" / "data"
    assert paths.database_path == local / "AzureSync" / "data" / "azure_sync.sqlite3"
    assert paths.log_dir == local / "AzureSync" / "logs"
    assert paths.run_dir == local / "AzureSync" / "run"
    assert paths.stop_file == local / "AzureSync" / "run" / "stop.request"
```

Run `pytest apps/launcher/tests/test_paths.py -v` and verify the package import
fails.

- [ ] **Step 2: Implement `AppPaths` and stable per-user names**

Use a frozen dataclass. Default `executable` is `Path(sys.executable)` when
`sys.frozen` is true and `Path(__file__).resolve().parents[2] / "AzureSync.exe"`
otherwise. Default local data is `Path(os.environ["LOCALAPPDATA"])`; allow
`AZURESYNC_LOCAL_APP_DATA` only as a test/smoke override.

Derive names without exposing usernames:

```python
@dataclass(frozen=True)
class InstanceNames:
    mutex: str
    stop_event: str

    @classmethod
    def for_data_root(cls, data_root: Path) -> "InstanceNames":
        suffix = hashlib.sha256(str(data_root.resolve()).lower().encode("utf-8")).hexdigest()[:16]
        return cls(
            mutex=fr"Local\AzureSync.Mutex.{suffix}",
            stop_event=fr"Local\AzureSync.Stop.{suffix}",
        )
```

- [ ] **Step 3: Write failing Windows primitive tests**

Mark the module Windows-only and test real kernel handles:

```python
@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher only")
def test_named_mutex_reports_second_acquisition():
    name = rf"Local\AzureSync.Test.{uuid.uuid4()}"
    first, first_created = NamedMutex.acquire(name)
    second, second_created = NamedMutex.acquire(name)
    try:
        assert first_created is True
        assert second_created is False
    finally:
        second.close()
        first.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher only")
def test_named_event_can_be_opened_and_signaled():
    name = rf"Local\AzureSync.Stop.Test.{uuid.uuid4()}"
    owner = NamedEvent.create(name)
    observer = NamedEvent.open(name)
    try:
        assert observer.wait(0) is False
        owner.set()
        assert observer.wait(1000) is True
    finally:
        observer.close()
        owner.close()
```

Run the file and verify missing classes fail collection.

- [ ] **Step 4: Implement Win32 handles with `ctypes`**

Load `kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)` only on
Windows. Configure `argtypes`/`restype` for `CreateMutexW`, `CreateEventW`,
`OpenEventW`, `SetEvent`, `WaitForSingleObject`, `CloseHandle`,
`CreateJobObjectW`, `SetInformationJobObject`, and `AssignProcessToJobObject`.

Use these constants:

```python
ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
```

`KillOnCloseJob.create` must populate
`JOBOBJECT_EXTENDED_LIMIT_INFORMATION.BasicLimitInformation.LimitFlags`, call
`SetInformationJobObject`, and close the handle on setup failure. Every class
implements context-manager methods and idempotent `.close()`.

- [ ] **Step 5: Test Job Object assignment and message abstraction**

Start a long-lived harmless child using `subprocess.Popen([sys.executable,
"-c", "import time; time.sleep(60)"])`, assign its `_handle`, close the job,
and assert the process exits within five seconds. Inject a fake `MessageBoxW`
call into `show_error` unit tests so CI never displays a real dialog.

- [ ] **Step 6: Run launcher primitive tests**

Run:

```powershell
pytest apps/launcher/tests/test_paths.py apps/launcher/tests/test_windows_control.py -v
```

Expected: all tests pass on Windows; Win32 integration tests skip elsewhere.

- [ ] **Step 7: Commit the Windows primitive slice**

```powershell
git add apps/launcher/azuresync_launcher/__init__.py apps/launcher/azuresync_launcher/paths.py apps/launcher/azuresync_launcher/windows_control.py apps/launcher/tests/test_paths.py apps/launcher/tests/test_windows_control.py
git commit -m "feat: add Windows launcher control primitives"
```

### Task 3: Add health-aware portable Waitress entry points

**Files:**
- Modify: `apps/sync-service/requirements.txt`
- Modify: `apps/api-read/requirements.txt`
- Modify: `apps/sync-service/app/routes.py`
- Modify: `apps/sync-service/tests/test_routes.py`
- Create: `apps/sync-service/portable_run.py`
- Create: `apps/sync-service/tests/test_portable_run.py`
- Create: `apps/api-read/portable_run.py`
- Create: `apps/api-read/tests/test_portable_run.py`

**Interfaces:**
- Adds `waitress==3.0.2` to both runtime requirement sets.
- Produces sync-service `GET /health -> {"status": "ok"}`.
- Produces `routes.shutdown_manual_syncs(wait: bool = True) -> None`.
- Each `portable_run.py` starts a Waitress server and watches the absolute file in `AZURESYNC_STOP_FILE` every 250 ms.
- Api-read portable entry discovers bundled web files at `Path(sys._MEIPASS) / "web"`.

- [ ] **Step 1: Write failing sync-service health and executor-shutdown tests**

Add:

```python
def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_shutdown_manual_syncs_delegates_to_executor(monkeypatch):
    executor = MagicMock()
    monkeypatch.setattr(routes, "_MANUAL_SYNC_EXECUTOR", executor)
    routes.shutdown_manual_syncs(wait=True)
    executor.shutdown.assert_called_once_with(wait=True, cancel_futures=False)
```

Run `pytest tests/test_routes.py -k "health or shutdown_manual" -v` and verify
404/missing-function failures.

- [ ] **Step 2: Implement health and controlled executor shutdown**

Add `/health` without opening a database connection. Implement
`shutdown_manual_syncs` exactly as the test specifies. Do not replace the
module executor during normal request handling.

- [ ] **Step 3: Write failing portable-run lifecycle tests**

In each app, patch `waitress.create_server` and inject a temporary stop file.
The fake server exposes `.run()` and `.close()`. For sync-service, also patch
schema initialization, scheduler `.start()`/`.shutdown(wait=True)`, and
`shutdown_manual_syncs(wait=True)`. Execute `portable_run.main` in a thread,
create the stop file, and assert server close plus all shutdown calls happen.

For api-read, set a fake `sys._MEIPASS` containing `web/index.html` and assert
`create_app` receives that path. Both tests assert a missing
`AZURESYNC_STOP_FILE` raises `RuntimeError("AZURESYNC_STOP_FILE is required")`
before binding a port.

- [ ] **Step 4: Implement the portable service entry points**

Both entry points use this lifecycle shape:

```python
def _wait_for_stop(stop_file: Path) -> None:
    while not stop_file.exists():
        time.sleep(0.25)


def _serve_in_thread(server) -> threading.Thread:
    thread = threading.Thread(target=server.run, name="portable-waitress")
    thread.start()
    return thread
```

Sync service `main()` initializes schema, creates one DPAPI protector, passes
it to `create_app` and `build_scheduler`, starts the scheduler and server,
waits for the stop file, calls `server.close()`,
`scheduler.shutdown(wait=True)`, `shutdown_manual_syncs(wait=True)`, and joins
the server thread. Api-read creates the app with the bundled web path, closes
the server after the same stop signal, and joins. Both bind only to
`127.0.0.1` and use configured ports.

In `finally`, close the server and scheduler only when they were successfully
created; do not log the complete child environment.

- [ ] **Step 5: Run portable server tests and backend regressions**

Run:

```powershell
Set-Location apps/sync-service
pytest tests/test_portable_run.py tests/test_routes.py tests/test_sync_service.py -v
Set-Location ../api-read
pytest tests/test_portable_run.py tests/test_routes.py tests/test_readonly_guardrail.py -v
```

Expected: controlled shutdown and health tests pass; existing request-scoped
DB and read-only guarantees remain green.

- [ ] **Step 6: Commit the portable server slice**

```powershell
git add apps/sync-service/requirements.txt apps/sync-service/app/routes.py apps/sync-service/portable_run.py apps/sync-service/tests/test_routes.py apps/sync-service/tests/test_portable_run.py apps/api-read/requirements.txt apps/api-read/portable_run.py apps/api-read/tests/test_portable_run.py
git commit -m "feat: add portable service entry points"
```

### Task 4: Implement service supervision, launcher, and stop alias

**Files:**
- Create: `apps/launcher/azuresync_launcher/supervisor.py`
- Create: `apps/launcher/azuresync_launcher/main.py`
- Create: `apps/launcher/entrypoint.py`
- Create: `apps/launcher/tests/test_supervisor.py`
- Create: `apps/launcher/tests/test_main.py`

**Interfaces:**
- Produces `ServiceSpec(name, executable, health_url, stdout_path, stderr_path)`.
- Produces `LauncherConfig(paths, names, startup_timeout=30.0, poll_interval=0.25, shutdown_timeout=30.0)`.
- Produces `ServiceSupervisor.start()`, `.wait_until_healthy()`, `.monitor_until_stop()`, and `.stop()`.
- Produces `main.launch() -> int` and `main.request_stop() -> int`.
- `entrypoint.py` dispatches by frozen executable basename: `StopAzureSync` calls `request_stop`; every other name calls `launch`.

- [ ] **Step 1: Write failing supervisor startup tests with injected boundaries**

Use fakes for `popen`, `urlopen`, monotonic clock, sleep, browser, job, and
event. Cover:

```python
def test_start_passes_only_portable_runtime_configuration(supervisor, paths):
    supervisor.start()
    sync_env = supervisor.popen_calls[0].env
    api_env = supervisor.popen_calls[1].env

    assert sync_env["DATABASE_URL"] == ""
    assert sync_env["SQLITE_DATABASE_PATH"] == str(paths.database_path)
    assert sync_env["AZURESYNC_STOP_FILE"] == str(paths.stop_file)
    assert api_env["API_READ_PORT"] == "5173"
    assert api_env["SYNC_SERVICE_BASE_URL"] == "http://127.0.0.1:5000"
    assert "AZURE_DEVOPS_API_KEY" not in sync_env
    assert "AZURE_DEVOPS_API_KEY" not in api_env


def test_waits_for_both_health_checks_before_opening_browser(supervisor):
    supervisor.health_results.extend([False, True, False, True])
    supervisor.start()
    supervisor.wait_until_healthy()
    assert supervisor.browser_calls == ["http://127.0.0.1:5173"]
```

Add tests for port 5000/5173 occupied before spawn, internal executable
missing, child exit before health, 30-second timeout, and partial-start cleanup.

- [ ] **Step 2: Implement `ServiceSupervisor` startup and readiness**

Define services from `AppPaths`. Open append-mode UTF-8 log files before
`Popen`, pass `cwd=executable.parent`, `creationflags=CREATE_NO_WINDOW`, and
the minimal environment described in the test. Assign each returned
`process._handle` to the Job Object immediately.

Keep construction behind these methods so tests inject all side effects:

```python
class ServiceSupervisor:
    def __init__(
        self,
        config: LauncherConfig,
        *,
        popen=subprocess.Popen,
        urlopen=urllib.request.urlopen,
        monotonic=time.monotonic,
        sleep=time.sleep,
        open_browser=webbrowser.open,
        job_factory=KillOnCloseJob.create,
    ):
        ...

    def _child_environment(self) -> dict[str, str]:
        return {
            "DATABASE_URL": "",
            "SQLITE_DATABASE_PATH": str(self.config.paths.database_path),
            "SYNC_SERVICE_BASE_URL": "http://127.0.0.1:5000",
            "API_READ_HOST": "127.0.0.1",
            "API_READ_PORT": "5173",
            "AZURESYNC_STOP_FILE": str(self.config.paths.stop_file),
        }
```

Check a port with a temporary socket bind to `127.0.0.1` before spawning.
Health is successful only on HTTP 200 and JSON `{"status": "ok"}`. On timeout
or early exit, create `stop.request`, close/terminate children, and raise a
`LauncherError` containing the service name and log path but no environment.

- [ ] **Step 3: Write failing monitor and stop tests**

Test these state transitions:

```python
def test_stop_event_requests_graceful_child_shutdown(supervisor, stop_event, paths):
    supervisor.start()
    stop_event.set()
    supervisor.monitor_until_stop()
    assert paths.stop_file.exists()
    assert all(process.wait_timeout == 30.0 for process in supervisor.processes)


def test_child_crash_stops_peer_and_reports_log(supervisor):
    supervisor.start()
    supervisor.processes[0].poll_result = 17
    with pytest.raises(LauncherError, match="sync-service"):
        supervisor.monitor_until_stop()
    assert supervisor.stop_was_called is True
```

`stop()` first writes the stop file atomically, waits for both children until
the shared 30-second deadline, terminates survivors, waits five more seconds,
then closes the Job Object and log handles.

- [ ] **Step 4: Implement monitor and deterministic cleanup**

Poll stop event and child status every 250 ms. Use a single idempotent cleanup
path from normal stop, timeout, startup error, child crash, and `finally`.
Delete a stale stop file before starting children and after both children exit.
Closing the Job Object is the last cleanup action.

- [ ] **Step 5: Write failing launcher/stop entry tests**

Test:

- first launch acquires the mutex, creates the manual-reset stop event, starts
  the supervisor, opens the browser after health, and monitors;
- second launch cannot acquire the mutex, waits for api-read health for up to
  30 seconds, opens the browser, and does not spawn children;
- unhealthy existing instance shows a native error and returns 1;
- `request_stop` opens the per-user event, signals it, and returns 0;
- stop with no instance shows `AzureSync is not running` and returns 1; and
- executable basename `StopAzureSync.exe` selects `request_stop`.

All tests inject `show_error` and `webbrowser.open`, so they display no GUI.

- [ ] **Step 6: Implement `main.py` and `entrypoint.py`**

Use this dispatch boundary:

```python
def entrypoint() -> int:
    executable_name = Path(sys.executable).stem.lower() if getattr(sys, "frozen", False) else "azuresync"
    return request_stop() if executable_name == "stopazuresync" else launch()


if __name__ == "__main__":
    raise SystemExit(entrypoint())
```

`launch` catches only `LauncherError`/`OSError`, writes the traceback to
`logs/launcher-error.log`, shows a short MessageBox with that path, and returns
1. It must not serialize environment variables. On success it returns 0 after
the monitored processes exit.

- [ ] **Step 7: Run all launcher tests**

Run:

```powershell
pytest apps/launcher/tests -v
```

Expected: unit tests pass; real Windows mutex/event/job integration passes on
Windows and skips elsewhere.

- [ ] **Step 8: Commit the launcher behavior**

```powershell
git add apps/launcher/azuresync_launcher/supervisor.py apps/launcher/azuresync_launcher/main.py apps/launcher/entrypoint.py apps/launcher/tests/test_supervisor.py apps/launcher/tests/test_main.py
git commit -m "feat: supervise portable AzureSync services"
```

### Task 5: Build the frozen service folders and reproducible ZIP

**Files:**
- Create: `requirements-build.txt`
- Create: `packaging/launcher.spec`
- Create: `packaging/sync-service.spec`
- Create: `packaging/api-read.spec`
- Create: `scripts/build-portable.ps1`
- Create: `scripts/smoke-portable.ps1`
- Modify: `.gitignore`

**Interfaces:**
- Produces `dist/AzureSync-win-x64/` with two user-facing executables and two internal onedir service distributions.
- Produces `dist/AzureSync-win-x64.zip` and `dist/AzureSync-win-x64.zip.sha256`.
- Supports optional `-SignToolPath` plus `-CertificateThumbprint`; neither is accepted alone.
- Smoke test supports `AZURESYNC_LOCAL_APP_DATA` to isolate data in a temporary directory.

- [ ] **Step 1: Pin build dependencies and ignore generated output**

Create:

```text
# requirements-build.txt
pyinstaller==6.21.0
```

Add `.build/`, `build/`, and `dist/` to `.gitignore`. Confirm Task 3 already
pins `waitress==3.0.2` in both application requirement files.

- [ ] **Step 2: Write the three PyInstaller specs**

`launcher.spec` analyzes `apps/launcher/entrypoint.py` with
`pathex=["apps/launcher"]`, `console=False`, name `AzureSync`, and a COLLECT
named `AzureSync-launcher`. It includes no app source trees as data.

`sync-service.spec` analyzes `apps/sync-service/portable_run.py` with
`pathex=["apps/sync-service"]`, includes `app/templates` and `app/static` as
data, uses `console=False`, and COLLECTs to `sync-service`.

`api-read.spec` analyzes `apps/api-read/portable_run.py` with
`pathex=["apps/api-read"]`, includes `apps/web-read/dist` at destination
`web`, uses `console=False`, and COLLECTs to `api-read`.

Use this exact onedir shape in each spec, changing entry, data, and names as
described above:

```python
from pathlib import Path

ROOT = Path(SPECPATH).parent.parent
a = Analysis(
    [str(ROOT / "apps" / "launcher" / "entrypoint.py")],
    pathex=[str(ROOT / "apps" / "launcher")],
    binaries=[],
    datas=[],
    hiddenimports=[],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AzureSync",
    console=False,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AzureSync-launcher",
)
```

Use this complete body for `sync-service.spec`:

```python
from pathlib import Path

ROOT = Path(SPECPATH).parent.parent
a = Analysis(
    [str(ROOT / "apps" / "sync-service" / "portable_run.py")],
    pathex=[str(ROOT / "apps" / "sync-service")],
    binaries=[],
    datas=[
        (str(ROOT / "apps" / "sync-service" / "app" / "templates"), "app/templates"),
        (str(ROOT / "apps" / "sync-service" / "app" / "static"), "app/static"),
    ],
    hiddenimports=[],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="sync-service",
    console=False,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="sync-service",
)
```

Use this complete body for `api-read.spec`:

```python
from pathlib import Path

ROOT = Path(SPECPATH).parent.parent
a = Analysis(
    [str(ROOT / "apps" / "api-read" / "portable_run.py")],
    pathex=[str(ROOT / "apps" / "api-read")],
    binaries=[],
    datas=[(str(ROOT / "apps" / "web-read" / "dist"), "web")],
    hiddenimports=[],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="api-read",
    console=False,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="api-read",
)
```

All three specs set `upx=False` to reduce antivirus variability and rely on
PyInstaller's isolated PYZ rather than copying `.py` files as data.

- [ ] **Step 3: Implement preflight and test phases in `build-portable.ps1`**

The script must use `$PSScriptRoot` to resolve the repository, set
`$ErrorActionPreference = 'Stop'`, and reject non-AMD64 Windows. Parse
`python --version` and `node --version`; reject Python below 3.12 and Node
below 22.

Create `.build\portable-venv`, install all three requirement files plus
`requirements-build.txt`, run sync/api pytest, run `npm ci`, `npm test`, and
`npm run build`. Do not use the user's global Python site-packages.

The preflight must use explicit version objects:

```powershell
$pythonVersion = [version]((& python -c "import platform; print(platform.python_version())").Trim())
$nodeVersion = [version]((& node -p "process.versions.node").Trim())
$pythonBits = (& python -c "import struct; print(struct.calcsize('P') * 8").Trim()
$nodeArchitecture = (& node -p "process.arch").Trim()
if ($pythonVersion -lt [version]'3.12') { throw 'Python x64 3.12 or newer is required.' }
if ($nodeVersion -lt [version]'22.0') { throw 'Node.js x64 22 or newer is required.' }
if ([Environment]::Is64BitOperatingSystem -ne $true) { throw 'Windows x64 is required.' }
if ($pythonBits -ne '64') { throw 'Python must be x64.' }
if ($nodeArchitecture -ne 'x64') { throw 'Node.js must be x64.' }
if ($PSVersionTable.PSVersion -lt [version]'5.1') { throw 'PowerShell 5.1 or newer is required.' }

python -m venv .build\portable-venv
$buildPython = Resolve-Path .build\portable-venv\Scripts\python.exe
& $buildPython -m pip install -r requirements-build.txt -r apps\sync-service\requirements.txt -r apps\api-read\requirements.txt
```

- [ ] **Step 4: Implement packaging and assembly**

Run PyInstaller 6.21.0 separately for each spec using unique work/output
directories. Assemble exactly:

```text
dist/AzureSync-win-x64/
  AzureSync.exe
  StopAzureSync.exe
  _internal/                 launcher onedir dependencies
  _services/
    sync-service/
      sync-service.exe
      _internal/
    api-read/
      api-read.exe
      _internal/
        web/
```

Copy `AzureSync.exe` to `StopAzureSync.exe`; both use the same `_internal` and
dispatch by executable basename. Copy each full service COLLECT folder without
flattening its `_internal` directory.

Use explicit assembly targets:

```powershell
$bundle = Join-Path $root 'dist\AzureSync-win-x64'
New-Item -ItemType Directory -Force -Path $bundle | Out-Null
Copy-Item "$launcherDist\AzureSync.exe" "$bundle\AzureSync.exe"
Copy-Item "$launcherDist\AzureSync.exe" "$bundle\StopAzureSync.exe"
Copy-Item "$launcherDist\_internal" "$bundle\_internal" -Recurse
Copy-Item $syncDist "$bundle\_services\sync-service" -Recurse
Copy-Item $apiDist "$bundle\_services\api-read" -Recurse
```

- [ ] **Step 5: Add optional Authenticode signing**

If both signing parameters are present, run `signtool sign /sha1
<thumbprint> /fd SHA256 /tr http://timestamp.digicert.com /td SHA256` for
`AzureSync.exe`, `StopAzureSync.exe`, `sync-service.exe`, and `api-read.exe`,
then run `signtool verify /pa` for each. If exactly one parameter is present,
stop with a parameter error before packaging. Do not accept certificate
passwords or PFX paths in this repository script.

- [ ] **Step 6: Write `smoke-portable.ps1` before invoking it from the build**

The smoke script:

1. extracts or consumes an assembled folder;
2. creates a unique temporary local-app-data root;
3. sets `AZURESYNC_LOCAL_APP_DATA` to that root;
4. replaces PATH with only `$env:SystemRoot\System32;$env:SystemRoot`;
5. asserts `Get-Command python,node,npm -ErrorAction SilentlyContinue` returns
   nothing;
6. starts `AzureSync.exe` hidden;
7. polls `http://127.0.0.1:5000/health`,
   `http://127.0.0.1:5173/health`, and `http://127.0.0.1:5173/` for 30 seconds;
8. asserts the SQLite file exists under the temporary root;
9. runs `StopAzureSync.exe`; and
10. asserts both internal service processes exit within 30 seconds.

Always restore PATH and remove only the verified unique temporary root in
`finally`. On failure, preserve a copy of logs under `.build\smoke-failure`.

- [ ] **Step 7: Finish ZIP/hash generation and run the build**

After smoke success, use `Compress-Archive` for
`dist\AzureSync-win-x64.zip`, calculate SHA-256 with `Get-FileHash`, and write
one line containing lowercase hash plus filename to
`dist\AzureSync-win-x64.zip.sha256`.

Run:

```powershell
.\scripts\build-portable.ps1
```

Expected: tests pass; folder, ZIP, hash, and smoke logs are produced. If
dependency installation is blocked by the sandbox/network, rerun only after
obtaining the required network approval.

- [ ] **Step 8: Inspect artifact contents and commit build sources**

Run:

```powershell
Get-ChildItem dist\AzureSync-win-x64
Get-FileHash dist\AzureSync-win-x64.zip -Algorithm SHA256
Get-Content dist\AzureSync-win-x64.zip.sha256
git status --short
```

Confirm no `.env`, `.git`, test file, PAT, or standalone `.py` source file is
in the ZIP. Commit only build sources:

```powershell
git add requirements-build.txt packaging/launcher.spec packaging/sync-service.spec packaging/api-read.spec scripts/build-portable.ps1 scripts/smoke-portable.ps1 .gitignore apps/sync-service/requirements.txt apps/api-read/requirements.txt
git commit -m "build: create Windows portable AzureSync bundle"
```

### Task 6: Document operation and perform final acceptance verification

**Files:**
- Modify: `README.md`
- Modify: `apps/sync-service/README.md`
- Modify: `apps/api-read/README.md`
- Modify: `apps/web-read/README.md`
- Verify: all files changed by this plan and the credential-storage plan

**Interfaces:**
- User instructions require only extract, run, configure PAT, use, and stop.
- Developer instructions describe exact build prerequisites and output.
- Acceptance evidence records suites, skipped database tests, artifact hash, and unsigned/signed state.

- [ ] **Step 1: Update portable user instructions**

Add a concise Windows section:

```text
1. Extract AzureSync-win-x64.zip to a writable local folder.
2. Run AzureSync.exe and wait for http://127.0.0.1:5173 to open.
3. Open Synchronization and save the Azure DevOps personal access token.
4. Use StopAzureSync.exe before moving or deleting the application folder.

Data and logs are retained under %LOCALAPPDATA%\AzureSync when the application
folder is replaced.
```

Document startup-error logs, fixed ports 5000/5173, SmartScreen caveat, and
the fact that copying SQLite to another Windows user does not make the PAT
decryptable.

- [ ] **Step 2: Document developer build and optional signing**

Document Windows x64, Python x64 3.12+, Node x64 22+, the exact
`build-portable.ps1` command, output paths, SHA verification, and optional
`-SignToolPath`/`-CertificateThumbprint`. Link to the official
[PyInstaller 6.21 manual](https://pyinstaller.org/en/stable/) and
[Waitress documentation](https://docs.pylonsproject.org/projects/waitress/en/latest/).

- [ ] **Step 3: Run all source-level suites**

Run:

```powershell
Set-Location apps/sync-service
pytest -v
Set-Location ../api-read
pytest -v
Set-Location ../web-read
npm test
npm run build
Set-Location ../..
pytest apps/launcher/tests -v
```

Expected: all configured tests pass. Report PostgreSQL tests skipped because
`TEST_DATABASE_URL` is absent as skips, not passes.

- [ ] **Step 4: Run final portable artifact verification**

Run:

```powershell
.\scripts\build-portable.ps1
.\scripts\smoke-portable.ps1 -BundlePath .\dist\AzureSync-win-x64
```

Open the ZIP listing and verify the two public executables, nested service
distributions, no source checkout, and no secret/config file. Compare
`Get-FileHash` with the `.sha256` file.

- [ ] **Step 5: Verify security and architecture guardrails**

Run:

```powershell
rg -n "AZURE_DEVOPS_API_KEY|get_ado_api_key" README.md apps/sync-service/app apps/sync-service/README.md apps/api-read/app apps/api-read/README.md apps/web-read/src apps/web-read/README.md apps/launcher/azuresync_launcher packaging scripts -g "!**/node_modules/**" -g "!**/dist/**"
rg -n "INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE" apps/api-read/app
git diff --check
git status --short
```

Expected: no legacy PAT configuration references, no write SQL in api-read,
no whitespace errors, and no generated artifacts staged.

- [ ] **Step 6: Commit documentation and record handoff facts**

```powershell
git add README.md apps/sync-service/README.md apps/api-read/README.md apps/web-read/README.md
git commit -m "docs: explain Windows portable distribution"
```

At handoff, report the ZIP path, SHA-256, whether Authenticode signing was
performed, all suite results, PostgreSQL skips, and the smoke-test result. Do
not claim compatibility with a corporate endpoint policy until the unsigned or
signed ZIP is exercised on a representative managed machine.
