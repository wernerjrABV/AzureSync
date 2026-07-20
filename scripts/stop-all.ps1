$ErrorActionPreference = 'Continue'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$stateDir = Join-Path $root 'logs\run-state'

foreach ($file in Get-ChildItem -LiteralPath $stateDir -Filter '*.pid' -ErrorAction SilentlyContinue) {
    $processId = [int](Get-Content -LiteralPath $file.FullName)
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $file.FullName -Force -ErrorAction SilentlyContinue
}
Write-Host 'Serviços encerrados.'
