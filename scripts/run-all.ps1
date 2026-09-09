param(
    [switch]$Visible
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$logDir = Join-Path $root 'logs'
$stateDir = Join-Path $root 'logs\run-state'
New-Item -ItemType Directory -Force -Path $logDir, $stateDir | Out-Null

function Start-AppProcess {
    param(
        [string]$Name,
        [string]$WorkingDirectory,
        [string]$FilePath,
        [string[]]$ArgumentList
    )

    $stdout = Join-Path $logDir "$Name.out.log"
    $stderr = Join-Path $logDir "$Name.err.log"
    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr -WindowStyle Hidden -PassThru
    $process.Id | Set-Content -LiteralPath (Join-Path $stateDir "$Name.pid")
    Write-Host "$Name iniciado (PID $($process.Id)). Logs: logs/$Name.*.log"
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python não foi encontrado. Instale Python e tente novamente.'
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw 'Node.js/npm não foi encontrado. Instale Node.js e tente novamente.'
}

function Resolve-Python {
    param([string]$AppDirectory)
    $venvPython = Join-Path $AppDirectory '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $venvPython) { return $venvPython }
    if (Get-Command python -ErrorAction SilentlyContinue) { return 'python' }
    throw 'Python não foi encontrado. Execute scripts/install.ps1 ou instale Python 3.12+.'
}

$syncDirectory = Join-Path $root 'apps\sync-service'
$apiDirectory = Join-Path $root 'apps\api-read'
$webDirectory = Join-Path $root 'apps\web-read'
Start-AppProcess 'sync-service' $syncDirectory (Resolve-Python $syncDirectory) @('run.py')
Start-AppProcess 'api-read' $apiDirectory (Resolve-Python $apiDirectory) @('run.py')
Start-AppProcess 'web-read' $webDirectory 'npm.cmd' @('run', 'dev', '--', '--host', '127.0.0.1')

Start-Sleep -Seconds 3
if ($Visible) {
    Start-Process 'http://127.0.0.1:5173'
} else {
    Start-Process 'powershell.exe' -ArgumentList '-NoProfile', '-Command', 'Start-Process "http://127.0.0.1:5173"' -WindowStyle Hidden
}
Write-Host 'Sistema iniciado em http://127.0.0.1:5173'
