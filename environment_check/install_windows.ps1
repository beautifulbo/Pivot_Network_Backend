param(
    [string]$StateDir,
    [switch]$Apply,
    [switch]$SkipRemoteCheck,
    [switch]$RemoteEnsureUp,
    [string]$RemoteHost = "",
    [int]$RemotePort = 0,
    [string]$RemoteUser = "",
    [string]$RemotePassword = "",
    [string]$RemoteKeyPath = "",
    [string]$RemoteInterface = "",
    [string]$RemoteConfigPath = "",
    [string]$RemoteEndpointHost = "",
    [int]$RemoteEndpointPort = 0,
    [string]$ReportPath = "",
    [string]$LogPath = ""
)

$ErrorActionPreference = "Stop"

if (-not $LogPath) {
    $LogDir = "D:\AI\Pivot_backend_build_team\.cache\environment_check"
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $LogPath = Join-Path $LogDir "install_windows.log"
}

function Test-IsAdmin {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source

if (-not $pythonExe) {
    Write-Error "Python is required to run the environment bootstrap."
}

if ($Apply -and -not (Test-IsAdmin)) {
    $argList = @(
        '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $MyInvocation.MyCommand.Path)
    )
    if ($StateDir) { $argList += @('-StateDir', ('"{0}"' -f $StateDir)) }
    if ($SkipRemoteCheck) { $argList += '-SkipRemoteCheck' }
    if ($RemoteEnsureUp) { $argList += '-RemoteEnsureUp' }
    if ($RemoteHost) { $argList += @('-RemoteHost', ('"{0}"' -f $RemoteHost)) }
    if ($RemotePort) { $argList += @('-RemotePort', $RemotePort) }
    if ($RemoteUser) { $argList += @('-RemoteUser', ('"{0}"' -f $RemoteUser)) }
    if ($RemotePassword) { $argList += @('-RemotePassword', ('"{0}"' -f $RemotePassword)) }
    if ($RemoteKeyPath) { $argList += @('-RemoteKeyPath', ('"{0}"' -f $RemoteKeyPath)) }
    if ($RemoteInterface) { $argList += @('-RemoteInterface', ('"{0}"' -f $RemoteInterface)) }
    if ($RemoteConfigPath) { $argList += @('-RemoteConfigPath', ('"{0}"' -f $RemoteConfigPath)) }
    if ($RemoteEndpointHost) { $argList += @('-RemoteEndpointHost', ('"{0}"' -f $RemoteEndpointHost)) }
    if ($RemoteEndpointPort) { $argList += @('-RemoteEndpointPort', $RemoteEndpointPort) }
    if ($ReportPath) { $argList += @('-ReportPath', ('"{0}"' -f $ReportPath)) }
    $argList += @('-LogPath', ('"{0}"' -f $LogPath))
    $argList += '-Apply'
    $elevated = Start-Process powershell -Verb RunAs -ArgumentList $argList -PassThru -Wait
    Write-Output "Installer requested elevation and has finished. Review log: $LogPath"
    if (Test-Path $LogPath) {
        Write-Output "--- installer log tail ---"
        Get-Content -Tail 120 $LogPath
    }
    exit 0
}

Start-Transcript -Path $LogPath -Append | Out-Null

$bootstrapArgs = @()
if ($StateDir) { $bootstrapArgs += @('--state-dir', $StateDir) }
if ($Apply) { $bootstrapArgs += '--apply' }
if ($SkipRemoteCheck) { $bootstrapArgs += '--skip-remote-check' }
if ($RemoteEnsureUp) { $bootstrapArgs += '--remote-ensure-up' }
if ($RemoteHost) { $bootstrapArgs += @('--remote-host', $RemoteHost) }
if ($RemotePort) { $bootstrapArgs += @('--remote-port', $RemotePort) }
if ($RemoteUser) { $bootstrapArgs += @('--remote-user', $RemoteUser) }
if ($RemotePassword) { $bootstrapArgs += @('--remote-password', $RemotePassword) }
if ($RemoteKeyPath) { $bootstrapArgs += @('--remote-key-path', $RemoteKeyPath) }
if ($RemoteInterface) { $bootstrapArgs += @('--remote-interface', $RemoteInterface) }
if ($RemoteConfigPath) { $bootstrapArgs += @('--remote-config-path', $RemoteConfigPath) }
if ($RemoteEndpointHost) { $bootstrapArgs += @('--remote-endpoint-host', $RemoteEndpointHost) }
if ($RemoteEndpointPort) { $bootstrapArgs += @('--remote-endpoint-port', $RemoteEndpointPort) }
if ($ReportPath) { $bootstrapArgs += @('--report-path', $ReportPath) }

Write-Output "Running environment bootstrap (Windows)..."
try {
    & $pythonExe "$scriptDir\windows_bootstrap.py" @bootstrapArgs
}
finally {
    Stop-Transcript | Out-Null
}
