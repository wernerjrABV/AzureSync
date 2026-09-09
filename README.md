# Azure DevOps Sync Monorepo

Enterprise monorepo for syncing Azure DevOps work items into PostgreSQL and
(in future phases) exposing them for read-only consumption.

## Layout

```
apps/
  sync-service/      Flask app — syncs Azure DevOps → PostgreSQL.
                      The ONLY app in this repo authorized to write to
                      the database. See apps/sync-service/README.md.
packages/
  shared-contracts/       (placeholder) DTOs/schemas shared across apps.
  shared-config/          (placeholder) lint/formatter/convention templates.
  shared-observability/   (placeholder) logging/tracing/metrics helpers.
  shared-db-guidelines/   (placeholder) data-access documentation/utilities.
docs/
  architecture/       System-level architecture docs.
  adr/                Architecture Decision Records.
  standards/          Technology lifecycle / governance rules.
```

## Running the sync service

### Starting all apps on Windows

To start the sync service, read API, and web frontend at once, double-click
`scripts/run-all.cmd`. It runs the services without leaving a terminal window
open and launches the web interface at http://127.0.0.1:5173.

To stop the services later, run `scripts/stop-all.ps1` from PowerShell.
Runtime logs are written to the local `logs/` directory.

After the apps start, open the web application, select Synchronization, enter
the Azure DevOps personal access token in Azure DevOps credential, and choose
Save credential. The token is encrypted for the current Windows user and is not
stored in `.env`.

### Windows portable distribution

For the packaged Windows bundle:

1. Extract `AzureSync-win-x64.zip` to a writable local folder.
2. Run `AzureSync.exe` and wait for http://127.0.0.1:5173 to open.
3. Open Synchronization and save the Azure DevOps personal access token.
4. Use `StopAzureSync.exe` before moving or deleting the application folder.

The portable launcher keeps mutable state in `%LOCALAPPDATA%\AzureSync`, so
data and logs are retained when you replace the extracted application folder.
SQLite data is stored at `%LOCALAPPDATA%\AzureSync\data\azure_sync.sqlite3` and
logs are written to `%LOCALAPPDATA%\AzureSync\logs`.

The bundle uses fixed loopback ports: sync-service listens on `127.0.0.1:5000`
and the packaged read UI listens on `127.0.0.1:5173`. Startup fails if either
port is already in use. If launch fails, inspect
`%LOCALAPPDATA%\AzureSync\logs\launcher-error.log` first, then
`sync-service.stderr.log` and `api-read.stderr.log` in the same log directory.

Unsigned builds can trigger Windows SmartScreen on first launch. That prompt is
expected unless the bundle has been Authenticode-signed. The saved Azure DevOps
credential is encrypted with Windows DPAPI for the current Windows user, so
copying the SQLite file to another Windows user profile does not make the PAT
decryptable there.

```bash
python -m pip install --user uv
cd apps/sync-service
uv venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
.\.venv\Scripts\Activate.ps1
python .\run.py
```

Open http://127.0.0.1:5000. See `apps/sync-service/README.md` for env vars
and test setup.

## Running the read path

The read path consists of two apps: `apps/api-read` (read-only backend) and
`apps/web-read` (React frontend).

**Via PowerShell (Windows):**

```powershell
# Terminal 1: Start the read API
.\scripts\run-api-read.ps1

# Terminal 2: Start the web frontend
.\scripts\run-web-read.ps1
```

Open http://127.0.0.1:5173 (web-read default port). See `apps/api-read/README.md`
and `apps/web-read/README.md` for env vars and configuration. Full architecture
at `docs/architecture/read-path-architecture.md`.

## Building the Windows portable bundle

Portable packaging is supported on Windows x64 only and requires:

- PowerShell 5.1+
- Python x64 3.12+
- Node.js x64 22+

From the repo root, run:

```powershell
.\scripts\build-portable.ps1
```

Outputs:

- unpacked bundle: `dist\AzureSync-win-x64\`
- ZIP artifact: `dist\AzureSync-win-x64.zip`
- SHA-256 sidecar: `dist\AzureSync-win-x64.zip.sha256`

Verify the published ZIP hash with:

```powershell
Get-FileHash .\dist\AzureSync-win-x64.zip -Algorithm SHA256
Get-Content .\dist\AzureSync-win-x64.zip.sha256
```

Optional Authenticode signing is available during the same build:

```powershell
.\scripts\build-portable.ps1 `
  -SignToolPath 'C:\Program Files (x86)\Windows Kits\10\App Certification Kit\signtool.exe' `
  -CertificateThumbprint '<sha1-thumbprint>'
```

The build script signs `AzureSync.exe`, `StopAzureSync.exe`, and the packaged
service executables when both parameters are supplied. See the
[PyInstaller manual](https://pyinstaller.org/en/stable/) and
[Waitress documentation](https://docs.pylonsproject.org/projects/waitress/en/latest/)
for the underlying runtime/build tooling used by the bundle.

## Roadmap

**Complete:**
- `apps/sync-service` — the only database writer (syncs Azure DevOps to PostgreSQL).
- `apps/api-read` — read-only backend querying the same database.
- `apps/web-read` — frontend listing data via `apps/api-read`.
- Database index review for the read-heavy access pattern.

**Next:**

Each phase lands as its own design spec + implementation plan
(see `docs/superpowers/specs/` and `docs/superpowers/plans/`) — this repo is
built incrementally, not as a big-bang rewrite.

## Governance

- Architecture decisions: `docs/adr/`
- Technology lifecycle (semestral review, V-2 annual upgrade rule):
  `docs/standards/technology-lifecycle.md`
- Single-writer rule: `docs/adr/0002-single-writer.md`
