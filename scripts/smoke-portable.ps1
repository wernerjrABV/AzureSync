[CmdletBinding(DefaultParameterSetName = 'Bundle')]
param(
    [Parameter(Mandatory = $true, ParameterSetName = 'Bundle')]
    [string]$BundlePath,

    [Parameter(Mandatory = $true, ParameterSetName = 'Zip')]
    [string]$ZipPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function New-UniqueTempDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Prefix
    )

    $base = [IO.Path]::GetTempPath()
    $path = Join-Path $base ("{0}{1}" -f $Prefix, [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $path -Force | Out-Null
    return $path
}

function Test-SafeTempDirectory {
    param(
        [string]$Path,
        [string]$Prefix
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $false
    }

    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $tempRoot = [IO.Path]::GetTempPath().TrimEnd('\')
    $leaf = Split-Path -Path $resolved -Leaf
    return $resolved.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase) -and $leaf.StartsWith($Prefix, [System.StringComparison]::OrdinalIgnoreCase)
}

function Wait-ForHttpOk {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [datetime]$Deadline
    )

    while ((Get-Date) -lt $Deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                return
            }
        } catch {
        }
        Start-Sleep -Milliseconds 250
    }

    throw "Timed out waiting for $Url"
}

function Get-ProcessIdsByName {
    param(
        [string]$Name
    )

    $processes = Get-Process -Name $Name -ErrorAction SilentlyContinue
    if ($null -eq $processes) {
        return @()
    }
    return @($processes | ForEach-Object { $_.Id })
}

function Wait-ForProcessIds {
    param(
        [int[]]$ProcessIds,
        [datetime]$Deadline,
        [switch]$Disappear
    )

    if ($ProcessIds.Count -eq 0) {
        return
    }

    while ((Get-Date) -lt $Deadline) {
        $aliveIds = @()
        foreach ($processId in $ProcessIds) {
            if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
                $aliveIds += $processId
            }
        }

        if ($Disappear.IsPresent) {
            if ($aliveIds.Count -eq 0) {
                return
            }
        } elseif ($aliveIds.Count -eq $ProcessIds.Count) {
            return
        }

        Start-Sleep -Milliseconds 250
    }

    if ($Disappear.IsPresent) {
        throw "Timed out waiting for processes to exit: $($ProcessIds -join ', ')"
    }
    throw "Timed out waiting for processes to start: $($ProcessIds -join ', ')"
}

function Save-SmokeFailureArtifacts {
    param(
        [string]$Root,
        [string]$LocalAppDataRoot
    )

    $failureRoot = Join-Path $Root '.build\smoke-failure'
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $destination = Join-Path $failureRoot $timestamp
    New-Item -ItemType Directory -Path $destination -Force | Out-Null

    if ($LocalAppDataRoot -and (Test-Path -LiteralPath $LocalAppDataRoot)) {
        $logs = Join-Path $LocalAppDataRoot 'AzureSync\logs'
        if (Test-Path -LiteralPath $logs) {
            Copy-Item -LiteralPath $logs -Destination (Join-Path $destination 'logs') -Recurse -Force
        }
    }
}

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root

$bundlePathResolved = $null
$extractRoot = $null
$localAppDataRoot = $null
$launcherProcess = $null
$originalPath = $env:PATH
$syncProcessIds = @()
$apiProcessIds = @()

try {
    if ($PSCmdlet.ParameterSetName -eq 'Zip') {
        $zipPathResolved = (Resolve-Path -LiteralPath $ZipPath).Path
        $extractRoot = New-UniqueTempDirectory -Prefix 'azuresync-smoke-extract-'
        Expand-Archive -LiteralPath $zipPathResolved -DestinationPath $extractRoot -Force
        $bundleCandidate = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
        if ($null -eq $bundleCandidate) {
            throw "Smoke ZIP did not contain a top-level directory: $zipPathResolved"
        }
        $bundlePathResolved = $bundleCandidate.FullName
    } else {
        $bundlePathResolved = (Resolve-Path -LiteralPath $BundlePath).Path
    }

    $azureSyncExe = Join-Path $bundlePathResolved 'AzureSync.exe'
    $stopExe = Join-Path $bundlePathResolved 'StopAzureSync.exe'
    if (-not (Test-Path -LiteralPath $azureSyncExe)) {
        throw "Bundle is missing AzureSync.exe: $bundlePathResolved"
    }
    if (-not (Test-Path -LiteralPath $stopExe)) {
        throw "Bundle is missing StopAzureSync.exe: $bundlePathResolved"
    }

    $localAppDataRoot = New-UniqueTempDirectory -Prefix 'azuresync-smoke-localappdata-'
    $env:AZURESYNC_LOCAL_APP_DATA = $localAppDataRoot
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"

    if (Get-Command python -ErrorAction SilentlyContinue) {
        throw 'python must not be resolvable from PATH during smoke test.'
    }
    if (Get-Command node -ErrorAction SilentlyContinue) {
        throw 'node must not be resolvable from PATH during smoke test.'
    }
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        throw 'npm must not be resolvable from PATH during smoke test.'
    }

    $beforeSyncIds = Get-ProcessIdsByName -Name 'sync-service'
    $beforeApiIds = Get-ProcessIdsByName -Name 'api-read'

    $launcherProcess = Start-Process -FilePath $azureSyncExe -WindowStyle Hidden -PassThru

    $deadline = (Get-Date).AddSeconds(30)
    Wait-ForHttpOk -Url 'http://127.0.0.1:5000/health' -Deadline $deadline
    Wait-ForHttpOk -Url 'http://127.0.0.1:5173/health' -Deadline $deadline
    Wait-ForHttpOk -Url 'http://127.0.0.1:5173/' -Deadline $deadline

    $syncProcessIds = @(Get-ProcessIdsByName -Name 'sync-service' | Where-Object { $_ -notin $beforeSyncIds })
    $apiProcessIds = @(Get-ProcessIdsByName -Name 'api-read' | Where-Object { $_ -notin $beforeApiIds })

    if ($syncProcessIds.Count -eq 0) {
        throw 'Smoke test did not observe a sync-service process.'
    }
    if ($apiProcessIds.Count -eq 0) {
        throw 'Smoke test did not observe an api-read process.'
    }

    $databasePath = Join-Path $localAppDataRoot 'AzureSync\data\azure_sync.sqlite3'
    if (-not (Test-Path -LiteralPath $databasePath)) {
        throw "SQLite database was not created: $databasePath"
    }

    $stopProcess = Start-Process -FilePath $stopExe -WindowStyle Hidden -PassThru -Wait
    if ($stopProcess.ExitCode -ne 0) {
        throw "StopAzureSync.exe exited with code $($stopProcess.ExitCode)."
    }

    $shutdownDeadline = (Get-Date).AddSeconds(30)
    Wait-ForProcessIds -ProcessIds $syncProcessIds -Deadline $shutdownDeadline -Disappear
    Wait-ForProcessIds -ProcessIds $apiProcessIds -Deadline $shutdownDeadline -Disappear
} catch {
    Save-SmokeFailureArtifacts -Root $root -LocalAppDataRoot $localAppDataRoot
    throw
} finally {
    $env:PATH = $originalPath
    Remove-Item Env:AZURESYNC_LOCAL_APP_DATA -ErrorAction SilentlyContinue

    if ($launcherProcess -and -not $launcherProcess.HasExited) {
        try {
            Stop-Process -Id $launcherProcess.Id -Force -ErrorAction Stop
        } catch {
        }
    }

    if ($localAppDataRoot -and (Test-Path -LiteralPath $localAppDataRoot) -and (Test-SafeTempDirectory -Path $localAppDataRoot -Prefix 'azuresync-smoke-localappdata-')) {
        Remove-Item -LiteralPath $localAppDataRoot -Recurse -Force
    }

    if ($extractRoot -and (Test-Path -LiteralPath $extractRoot) -and (Test-SafeTempDirectory -Path $extractRoot -Prefix 'azuresync-smoke-extract-')) {
        Remove-Item -LiteralPath $extractRoot -Recurse -Force
    }
}
