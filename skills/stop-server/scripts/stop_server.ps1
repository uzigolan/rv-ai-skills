$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path "$scriptDir\..\..\.."

$sandboxDir = Join-Path $repoRoot ".sandbox"
$pidFile = Join-Path $sandboxDir "server.pid"

if (!(Test-Path $pidFile)) {
  Write-Host "No PID file found at $pidFile."
  exit 1
}

$serverPid = Get-Content $pidFile | Select-Object -First 1
if ($serverPid -match '^\d+$') {
  try {
    Stop-Process -Id $serverPid -Force -ErrorAction Stop
    Remove-Item $pidFile -Force
    Write-Host "Stopped server PID $serverPid."
  } catch {
    Write-Host "Failed to stop PID $serverPid. It may already be stopped."
  }
} else {
  Write-Host "PID file is invalid."
}
