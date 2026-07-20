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

Start-AppProcess 'sync-service' (Join-Path $root 'apps\sync-service') 'python' @('run.py')
Start-AppProcess 'api-read' (Join-Path $root 'apps\api-read') 'python' @('run.py')
Start-AppProcess 'web-read' (Join-Path $root 'apps\web-read') 'npm.cmd' @('run', 'dev', '--', '--host', '127.0.0.1')

Start-Sleep -Seconds 3
if ($Visible) {
    Start-Process 'http://127.0.0.1:5173'
} else {
    Start-Process 'powershell.exe' -ArgumentList '-NoProfile', '-Command', 'Start-Process "http://127.0.0.1:5173"' -WindowStyle Hidden
}
Write-Host 'Sistema iniciado em http://127.0.0.1:5173'
