[CmdletBinding()]
param(
    [string]$InstallRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]$Branch = 'main'
)

$ErrorActionPreference = 'Stop'
$repo = 'wernerjrABV/AzureSync'
$archiveUrl = "https://github.com/$repo/archive/refs/heads/$Branch.zip"
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("azuresync-update-{0}" -f ([guid]::NewGuid()))
$archivePath = Join-Path $tempRoot 'source.zip'
$extractRoot = Join-Path $tempRoot 'extract'

try {
    New-Item -ItemType Directory -Path $tempRoot, $extractRoot -Force | Out-Null
    Invoke-WebRequest -Uri $archiveUrl -OutFile $archivePath -UseBasicParsing
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extractRoot -Force
    $sourceRoot = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
    if ($null -eq $sourceRoot) { throw 'O pacote de atualização não contém uma pasta de projeto.' }

    & (Join-Path $InstallRoot 'scripts\stop-all.ps1')
    Start-Sleep -Seconds 2
    Copy-Item -Path (Join-Path $sourceRoot.FullName '*') -Destination $InstallRoot -Recurse -Force

    foreach ($app in @('sync-service', 'api-read')) {
        $appRoot = Join-Path $InstallRoot "apps\$app"
        $venv = Join-Path $appRoot '.venv'
        & python -m venv $venv
        & (Join-Path $venv 'Scripts\python.exe') -m pip install -r (Join-Path $appRoot 'requirements.txt')
    }
    Push-Location (Join-Path $InstallRoot 'apps\web-read')
    try { & npm.cmd ci --no-audit --no-fund } finally { Pop-Location }
    Start-Process powershell.exe -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $InstallRoot 'scripts\run-all.ps1') -WorkingDirectory $InstallRoot -WindowStyle Hidden
}
finally {
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
