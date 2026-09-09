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

function Assert-RequiredRuntimes {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw 'Python 3.12+ não foi encontrado. Solicite Python 3.12 ou superior pelo portal de software da empresa e execute o instalador novamente.'
    }
    $pythonVersion = [version]((& python -c "import platform; print(platform.python_version())").Trim())
    if ($pythonVersion -lt [version]'3.12') {
        throw "Python $pythonVersion foi encontrado, mas o AzureSync requer Python 3.12+. Solicite a atualização pelo portal de software da empresa."
    }

    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($null -eq $nodeCommand -or $null -eq $npmCommand) {
        throw 'Node.js 22+ não foi encontrado. Solicite Node.js 22 ou superior pelo portal de software da empresa e execute o instalador novamente.'
    }
    $nodeVersion = [version]((& node -p "process.versions.node").Trim())
    if ($nodeVersion -lt [version]'22.0') {
        throw "Node.js $nodeVersion foi encontrado, mas o AzureSync requer Node.js 22+. Solicite a atualização pelo portal de software da empresa."
    }
}

function New-EngineeringPortfolioIcon {
    param([string]$Root)

    $iconDirectory = Join-Path $Root 'assets'
    $iconPath = Join-Path $iconDirectory 'engineering-portfolio.ico'
    if (Test-Path -LiteralPath $iconPath) {
        return $iconPath
    }
    try {
        Add-Type -AssemblyName System.Drawing
        New-Item -ItemType Directory -Path $iconDirectory -Force | Out-Null
        $bitmap = New-Object System.Drawing.Bitmap(256, 256)
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $graphics.Clear([System.Drawing.Color]::FromArgb(24, 48, 88))

        $gridPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(70, 125, 190), 2)
        for ($coordinate = 24; $coordinate -lt 256; $coordinate += 32) {
            $graphics.DrawLine($gridPen, $coordinate, 0, $coordinate, 256)
            $graphics.DrawLine($gridPen, 0, $coordinate, 256, $coordinate)
        }

        $roadmapPen = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 12)
        $roadmapPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $roadmapPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $points = @(
            (New-Object System.Drawing.Point(42, 188)),
            (New-Object System.Drawing.Point(92, 132)),
            (New-Object System.Drawing.Point(146, 160)),
            (New-Object System.Drawing.Point(214, 70))
        )
        $graphics.DrawLines($roadmapPen, $points)

        $nodeBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(245, 183, 57))
        $graphics.FillEllipse($nodeBrush, 198, 54, 32, 32)
        $bitmap.Save($iconPath, [System.Drawing.Imaging.ImageFormat]::Icon)

        $nodeBrush.Dispose()
        $roadmapPen.Dispose()
        $gridPen.Dispose()
        $graphics.Dispose()
        $bitmap.Dispose()
        return $iconPath
    }
    catch {
        Write-Warning 'Não foi possível gerar o ícone personalizado; usando um ícone nativo do Windows.'
        return $null
    }
}

function New-DesktopShortcut {
    param([string]$Root)

    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcutPath = Join-Path $desktop 'Engineering Portfolio.lnk'
    $runScript = Join-Path $Root 'scripts\run-all.ps1'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = (Get-Command powershell.exe).Source
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$runScript`""
    $shortcut.WorkingDirectory = $Root
    $iconPath = New-EngineeringPortfolioIcon -Root $Root
    if ($null -ne $iconPath) { $shortcut.IconLocation = "$iconPath,0" }
    else { $shortcut.IconLocation = "$env:SystemRoot\System32\imageres.dll,109" }
    $shortcut.Description = 'Iniciar o Engineering Portfolio'
    $shortcut.Save()
    Write-Host "Atalho criado na área de trabalho: $shortcutPath"
}

try {
    Assert-RequiredRuntimes

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

    New-DesktopShortcut -Root $installRootResolved

    Write-Host ''
    Write-Host 'AzureSync instalado com sucesso.' -ForegroundColor Green
    Write-Host "Para iniciar: & '$installRootResolved\scripts\run-all.ps1'"
    Write-Host "Para parar:   & '$installRootResolved\scripts\stop-all.ps1'"
    Write-Host 'A interface será aberta em http://127.0.0.1:5173.'
}
finally {
    if (Test-Path -LiteralPath $tempRoot) { Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
