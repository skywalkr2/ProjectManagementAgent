# Installs or updates PM Cockpit from a downloaded package file, then tells you how to start.
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1 pm_cockpit-<version>-py3-none-any.whl
# Needs uv (the Python package tool). Running it again with a newer file updates the app; workspaces are untouched.
param([Parameter(Mandatory = $true)][string]$Package)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $Package -PathType Leaf)) {
    Write-Error "Usage: install.ps1 <the downloaded .whl file>"
    exit 2
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "This needs uv, the Python package tool. Install it from its documentation, open a new terminal, and run this again."
    exit 1
}
uv tool install --force --python 3.12 $Package
uv tool update-shell | Out-Null
Write-Host ""
Write-Host "Installed. Open a new terminal, then:"
Write-Host "  cockpit demo                         try it on made-up data"
Write-Host "  cockpit init ~\cockpit\my-work       start your own workspace"
Write-Host "  cockpit serve -w ~\cockpit\my-work"
