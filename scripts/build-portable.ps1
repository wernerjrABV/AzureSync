[CmdletBinding()]
param(
    [string]$SignToolPath,
    [string]$CertificateThumbprint
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-SigningParameters {
    if ([string]::IsNullOrWhiteSpace($SignToolPath) -xor [string]::IsNullOrWhiteSpace($CertificateThumbprint)) {
        throw 'SignToolPath and CertificateThumbprint must be provided together.'
    }
}

function Assert-BuildPlatform {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'Windows AMD64 is required.'
    }
    if ([Environment]::Is64BitOperatingSystem -ne $true) {
        throw 'Windows x64 is required.'
    }
    if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
        throw 'Windows AMD64 is required.'
    }
    if ($PSVersionTable.PSVersion -lt [version]'5.1') {
        throw 'PowerShell 5.1 or newer is required.'
    }
}

function Assert-Toolchain {
    $pythonVersion = [version]((& python -c "import platform; print(platform.python_version())").Trim())
    $nodeVersion = [version]((& node -p "process.versions.node").Trim())
    $pythonBits = (& python -c "import struct; print(struct.calcsize('P') * 8)").Trim()
    $nodeArchitecture = (& node -p "process.arch").Trim()

    if ($pythonVersion -lt [version]'3.12') {
        throw 'Python x64 3.12 or newer is required.'
    }
    if ($nodeVersion -lt [version]'22.0') {
        throw 'Node.js x64 22 or newer is required.'
    }
    if ($pythonBits -ne '64') {
        throw 'Python must be x64.'
    }
    if ($nodeArchitecture -ne 'x64') {
        throw 'Node.js must be x64.'
    }
}

function Assert-PortablePrerequisites {
    param(
        [string]$Root
    )

    $requiredPaths = @(
        (Join-Path $Root 'packaging\launcher.spec'),
        (Join-Path $Root 'packaging\sync-service.spec'),
        (Join-Path $Root 'packaging\api-read.spec'),
        (Join-Path $Root 'apps\launcher\entrypoint.py'),
        (Join-Path $Root 'apps\sync-service\portable_run.py'),
        (Join-Path $Root 'apps\api-read\portable_run.py'),
        (Join-Path $Root 'apps\web-read\package.json'),
        (Join-Path $Root 'apps\web-read\package-lock.json')
    )

    foreach ($path in $requiredPaths) {
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Portable build prerequisite is missing: $path"
        }
    }
}

function Reset-Directory {
    param(
        [string]$Path
    )

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE."
    }
}

function Invoke-PyInstallerBuild {
    param(
        [string]$PythonExe,
        [string]$Root,
        [string]$SpecName
    )

    $specPath = Join-Path $Root ("packaging\{0}.spec" -f $SpecName)
    $workRoot = Join-Path $Root (".build\pyinstaller\{0}\build" -f $SpecName)
    $distRoot = Join-Path $Root (".build\pyinstaller\{0}\dist" -f $SpecName)

    Reset-Directory -Path $workRoot
    Reset-Directory -Path $distRoot

    Invoke-Checked { & $PythonExe -m PyInstaller --noconfirm --clean --workpath $workRoot --distpath $distRoot $specPath }

    return $distRoot
}

function Invoke-OptionalSigning {
    param(
        [string]$ResolvedSignToolPath,
        [string]$Thumbprint,
        [string[]]$ExecutablePaths
    )

    if ([string]::IsNullOrWhiteSpace($ResolvedSignToolPath)) {
        return
    }

    foreach ($filePath in $ExecutablePaths) {
        Invoke-Checked {
            & $ResolvedSignToolPath sign /sha1 $Thumbprint /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $filePath
        }
        Invoke-Checked {
            & $ResolvedSignToolPath verify /pa $filePath
        }
    }
}

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

Assert-SigningParameters
Assert-BuildPlatform
Assert-Toolchain
Assert-PortablePrerequisites -Root $root

$resolvedSignToolPath = $null
if (-not [string]::IsNullOrWhiteSpace($SignToolPath)) {
    $resolvedSignToolPath = (Resolve-Path -LiteralPath $SignToolPath).Path
}

$portableVenv = Join-Path $root '.build\portable-venv'
$buildRoot = Join-Path $root '.build'
$bundle = Join-Path $root 'dist\AzureSync-win-x64'
$zipPath = Join-Path $root 'dist\AzureSync-win-x64.zip'
$hashPath = Join-Path $root 'dist\AzureSync-win-x64.zip.sha256'

New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $root 'dist') -Force | Out-Null

if (Test-Path -LiteralPath $portableVenv) {
    Remove-Item -LiteralPath $portableVenv -Recurse -Force
}

Invoke-Checked { & python -m venv $portableVenv }
$buildPython = (Resolve-Path (Join-Path $portableVenv 'Scripts\python.exe')).Path

Invoke-Checked {
    & $buildPython -m pip install `
        -r (Join-Path $root 'requirements-build.txt') `
        -r (Join-Path $root 'apps\sync-service\requirements.txt') `
        -r (Join-Path $root 'apps\api-read\requirements.txt')
}

Push-Location (Join-Path $root 'apps\sync-service')
try {
    Invoke-Checked { & $buildPython -m pytest tests -v }
} finally {
    Pop-Location
}

Push-Location (Join-Path $root 'apps\api-read')
try {
    Invoke-Checked { & $buildPython -m pytest tests -v }
} finally {
    Pop-Location
}

Push-Location (Join-Path $root 'apps\web-read')
try {
    Invoke-Checked { & npm ci }
    Invoke-Checked { & npm test }
    Invoke-Checked { & npm run build }
} finally {
    Pop-Location
}

$launcherDistRoot = Invoke-PyInstallerBuild -PythonExe $buildPython -Root $root -SpecName 'launcher'
$syncDistRoot = Invoke-PyInstallerBuild -PythonExe $buildPython -Root $root -SpecName 'sync-service'
$apiDistRoot = Invoke-PyInstallerBuild -PythonExe $buildPython -Root $root -SpecName 'api-read'

$launcherDist = Join-Path $launcherDistRoot 'AzureSync-launcher'
$syncDist = Join-Path $syncDistRoot 'sync-service'
$apiDist = Join-Path $apiDistRoot 'api-read'

if (-not (Test-Path -LiteralPath $launcherDist)) {
    throw "Launcher PyInstaller output was not created: $launcherDist"
}
if (-not (Test-Path -LiteralPath $syncDist)) {
    throw "sync-service PyInstaller output was not created: $syncDist"
}
if (-not (Test-Path -LiteralPath $apiDist)) {
    throw "api-read PyInstaller output was not created: $apiDist"
}

Reset-Directory -Path $bundle
New-Item -ItemType Directory -Path (Join-Path $bundle '_services') -Force | Out-Null

Copy-Item (Join-Path $launcherDist 'AzureSync.exe') (Join-Path $bundle 'AzureSync.exe')
Copy-Item (Join-Path $launcherDist 'AzureSync.exe') (Join-Path $bundle 'StopAzureSync.exe')
Copy-Item (Join-Path $launcherDist '_internal') (Join-Path $bundle '_internal') -Recurse
Copy-Item $syncDist (Join-Path $bundle '_services\sync-service') -Recurse
Copy-Item $apiDist (Join-Path $bundle '_services\api-read') -Recurse

Invoke-OptionalSigning -ResolvedSignToolPath $resolvedSignToolPath -Thumbprint $CertificateThumbprint -ExecutablePaths @(
    (Join-Path $bundle 'AzureSync.exe'),
    (Join-Path $bundle 'StopAzureSync.exe'),
    (Join-Path $bundle '_services\sync-service\sync-service.exe'),
    (Join-Path $bundle '_services\api-read\api-read.exe')
)

Invoke-Checked { & (Join-Path $root 'scripts\smoke-portable.ps1') -BundlePath $bundle }

if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
if (Test-Path -LiteralPath $hashPath) {
    Remove-Item -LiteralPath $hashPath -Force
}

Compress-Archive -Path $bundle -DestinationPath $zipPath -Force
$hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText($hashPath, "$hash  AzureSync-win-x64.zip`n")

Write-Host "Portable bundle created at $bundle"
Write-Host "ZIP created at $zipPath"
Write-Host "SHA256 written to $hashPath"
