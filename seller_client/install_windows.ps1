param(
    [string]$StateDir,
    [switch]$Apply,
    [string]$LogPath = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$targetScript = Join-Path $repoRoot "environment_check\install_windows.ps1"

if (-not (Test-Path $targetScript)) {
    Write-Error "Expected installer entrypoint not found: $targetScript"
}

$forwardArgs = @{}
if ($StateDir) {
    $forwardArgs["StateDir"] = $StateDir
}
if ($Apply) {
    $forwardArgs["Apply"] = $true
}
if ($LogPath) {
    $forwardArgs["LogPath"] = $LogPath
}

& $targetScript @forwardArgs
