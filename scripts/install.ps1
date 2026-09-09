[CmdletBinding()]
param(
    [string]$Branch = 'main',
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'AzureSync\app')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$installRootResolved = [IO.Path]::GetFullPath($InstallRoot)
$repo = 'wernerjrABV/AzureSync'
$scriptRoot = $null
$usingLocalSource = $false
if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
    $scriptRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    $scriptRootResolved = [IO.Path]::GetFullPath($scriptRoot)
    $usingLocalSource = [string]::Equals($installRootResolved.TrimEnd('\'), $scriptRootResolved.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)
}
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
    if ($usingLocalSource -and (Test-Path -LiteralPath (Join-Path $scriptRoot '.git'))) {
        $sourceRoot = Get-Item -LiteralPath $scriptRoot
        Write-Host "Usando o clone local em $scriptRoot..."
    }
    else {
        New-Item -ItemType Directory -Path $tempRoot, $extractRoot -Force | Out-Null
        Write-Host "Baixando AzureSync ($Branch)..."
        try {
            Invoke-WebRequest -Uri $archiveUrl -OutFile $archivePath -UseBasicParsing
        }
        catch {
            if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw }
            Write-Host 'Download público indisponível; usando GitHub CLI autenticado...'
            Invoke-Checked { & gh api "repos/$repo/zipball/$Branch" --output $archivePath } 'Não foi possível baixar o repositório pelo GitHub CLI'
        }
        Expand-Archive -LiteralPath $archivePath -DestinationPath $extractRoot -Force
        $sourceRoot = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
        if ($null -eq $sourceRoot) { throw 'O arquivo do GitHub não contém uma pasta de projeto.' }

        New-Item -ItemType Directory -Path (Split-Path -Parent $InstallRoot) -Force | Out-Null
        if (Test-Path -LiteralPath $InstallRoot) { Remove-Item -LiteralPath $InstallRoot -Recurse -Force }
        Move-Item -LiteralPath $sourceRoot.FullName -Destination $InstallRoot
    }

    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw 'Python 3.12+ não foi encontrado. Instale-o e execute novamente.'
    }
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        throw 'Node.js 22+ não foi encontrado. Instale-o e execute novamente.'
    }

    foreach ($app in @('sync-service', 'api-read')) {
        $appRoot = Join-Path $installRootResolved "apps\$app"
        $venv = Join-Path $appRoot '.venv'
        Write-Host "Configurando dependências Python de $app..."
        Invoke-Checked { & python -m venv $venv } "Não foi possível criar o ambiente Python de $app"
        Invoke-Checked { & (Join-Path $venv 'Scripts\python.exe') -m pip install -r (Join-Path $appRoot 'requirements.txt') } "Não foi possível instalar as dependências de $app"
    }

    Write-Host 'Instalando dependências do frontend...'
    Push-Location (Join-Path $installRootResolved 'apps\web-read')
    try { Invoke-Checked { & npm.cmd ci --no-audit --no-fund } 'Não foi possível instalar as dependências do frontend' }
    finally { Pop-Location }

    Write-Host ''
    Write-Host 'AzureSync instalado com sucesso.' -ForegroundColor Green
    Write-Host "Para iniciar: & '$installRootResolved\scripts\run-all.ps1'"
    Write-Host "Para parar:   & '$installRootResolved\scripts\stop-all.ps1'"
    Write-Host 'A interface será aberta em http://127.0.0.1:5173.'
}
finally {
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
