[CmdletBinding()]
param(
    [string]$Branch = 'main',
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'AzureSync\app')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = 'wernerjrABV/AzureSync'
$archiveUrl = "https://github.com/$repo/archive/refs/heads/$Branch.zip"
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("azuresync-install-{0}" -f ([guid]::NewGuid()))
$archivePath = Join-Path $tempRoot 'source.zip'
$extractRoot = Join-Path $tempRoot 'extract'

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Message)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Message (exit code $LASTEXITCODE)." }
}

try {
    New-Item -ItemType Directory -Path $tempRoot, $extractRoot -Force | Out-Null
    Write-Host "Baixando AzureSync ($Branch)..."
    Invoke-WebRequest -Uri $archiveUrl -OutFile $archivePath -UseBasicParsing
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extractRoot -Force

    $sourceRoot = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
    if ($null -eq $sourceRoot) { throw 'O arquivo do GitHub não contém uma pasta de projeto.' }
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw 'Python 3.12+ não foi encontrado. Instale-o e execute novamente.'
    }
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        throw 'Node.js 22+ não foi encontrado. Instale-o e execute novamente.'
    }

    New-Item -ItemType Directory -Path (Split-Path -Parent $InstallRoot) -Force | Out-Null
    if (Test-Path -LiteralPath $InstallRoot) { Remove-Item -LiteralPath $InstallRoot -Recurse -Force }
    Move-Item -LiteralPath $sourceRoot.FullName -Destination $InstallRoot

    foreach ($app in @('sync-service', 'api-read')) {
        $appRoot = Join-Path $InstallRoot "apps\$app"
        $venv = Join-Path $appRoot '.venv'
        Write-Host "Configurando dependências Python de $app..."
        Invoke-Checked { & python -m venv $venv } "Não foi possível criar o ambiente Python de $app"
        Invoke-Checked { & (Join-Path $venv 'Scripts\python.exe') -m pip install -r (Join-Path $appRoot 'requirements.txt') } "Não foi possível instalar as dependências de $app"
    }

    Write-Host 'Instalando dependências do frontend...'
    Push-Location (Join-Path $InstallRoot 'apps\web-read')
    try { Invoke-Checked { & npm.cmd ci --no-audit --no-fund } 'Não foi possível instalar as dependências do frontend' }
    finally { Pop-Location }

    Write-Host ''
    Write-Host 'AzureSync instalado com sucesso.' -ForegroundColor Green
    Write-Host "Para iniciar: & '$InstallRoot\scripts\run-all.ps1'"
    Write-Host "Para parar:   & '$InstallRoot\scripts\stop-all.ps1'"
    Write-Host 'A interface será aberta em http://127.0.0.1:5173.'
}
finally {
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
