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

function Reset-DesktopShortcut {
    param([string]$Root)

    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcutPath = Join-Path $desktop 'Engineering Portfolio.lnk'
    if (Test-Path -LiteralPath $shortcutPath) {
        Remove-Item -LiteralPath $shortcutPath -Force
    }

    $runScript = Join-Path $Root 'scripts\run-all.ps1'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = (Get-Command powershell.exe).Source
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$runScript`""
    $shortcut.WorkingDirectory = $Root
    $iconPath = Join-Path $Root 'assets\engineering-portfolio.ico'
    if (Test-Path -LiteralPath $iconPath) {
        $shortcut.IconLocation = "$iconPath,0"
    }
    else {
        $shortcut.IconLocation = "$env:SystemRoot\System32\imageres.dll,109"
    }
    $shortcut.Description = 'Iniciar o Engineering Portfolio'
    $shortcut.Save()
}

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
    Reset-DesktopShortcut -Root $InstallRoot
    Start-Process powershell.exe -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $InstallRoot 'scripts\run-all.ps1') -WorkingDirectory $InstallRoot -WindowStyle Hidden
}
finally {
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
