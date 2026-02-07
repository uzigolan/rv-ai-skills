$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path "$scriptDir\..\..\.."

$sandboxDir = Join-Path $repoRoot ".sandbox"
$venvDir = Join-Path $sandboxDir "venv"
$pidFile = Join-Path $sandboxDir "server.pid"
$logFile = Join-Path $sandboxDir "server.log"
$errFile = Join-Path $sandboxDir "server.err.log"

New-Item -ItemType Directory -Force -Path $sandboxDir | Out-Null

if (!(Test-Path $venvDir)) {
  py -3 -m venv $venvDir
}

$python = Join-Path $venvDir "Scripts\python.exe"

& $python -m pip install -r (Join-Path $repoRoot "requirements.txt")

if (Test-Path $pidFile) {
  Write-Host "Server PID file already exists at $pidFile. Stop it first if needed."
  exit 1
}

$process = Start-Process -FilePath $python `
  -ArgumentList @("-m", "app.server", "--config", (Join-Path $repoRoot "config.ini")) `
  -WorkingDirectory $repoRoot `
  -RedirectStandardOutput $logFile `
  -RedirectStandardError $errFile `
  -PassThru

if ($process -and $process.Id) {
  $process.Id | Set-Content -Encoding ASCII $pidFile
  Write-Host "Server started with PID $($process.Id). Log: $logFile Error: $errFile"
} else {
  Write-Host "Failed to start server. Check log at $logFile."
  exit 1
}
