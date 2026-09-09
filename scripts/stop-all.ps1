$ErrorActionPreference = 'Continue'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$stateDir = Join-Path $root 'logs\run-state'

$rootMarker = $root.TrimEnd('\').ToLowerInvariant()
try {
    Get-CimInstance Win32_Process -ErrorAction Stop |
        Where-Object {
            $_.Name -in @('python.exe', 'node.exe', 'esbuild.exe') -and
            (($null -ne $_.ExecutablePath -and $_.ExecutablePath.ToLowerInvariant().StartsWith($rootMarker)) -or
             ($null -ne $_.CommandLine -and $_.CommandLine.ToLowerInvariant().Contains($rootMarker)))
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}
catch {
    Write-Warning 'Não foi possível inspecionar todos os processos filhos.'
}
Start-Sleep -Seconds 2

foreach ($file in Get-ChildItem -LiteralPath $stateDir -Filter '*.pid' -ErrorAction SilentlyContinue) {
    $processId = [int](Get-Content -LiteralPath $file.FullName)
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $file.FullName -Force -ErrorAction SilentlyContinue
}
Write-Host 'Serviços encerrados.'
