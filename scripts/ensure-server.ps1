# Make sure one tqd-browser API server answers on 127.0.0.1:8000, starting it if needed.
#
#   powershell -NoProfile -File scripts/ensure-server.ps1
#
# A running server (desktop app or server mode) is reused and left running for later runs. The
# port is fixed: if something else holds it without answering, this script stops with an error
# instead of starting a second server elsewhere.

$ErrorActionPreference = 'Stop'
$Port = 8000
$Health = "http://127.0.0.1:$Port/api/v1/health"
$Root = Split-Path -Parent $PSScriptRoot
$DataDir = if ($env:TQD_AUTOMATION_DIR) { $env:TQD_AUTOMATION_DIR } else { Join-Path $Root 'automation_data' }
$PidFile = Join-Path $DataDir 'server.pid'

function Test-Health {
    try {
        Invoke-RestMethod -Uri $Health -TimeoutSec 3 | Out-Null
        return $true
    } catch {
        return $false
    }
}

if (Test-Health) {
    Write-Output "server already answering on port $Port"
    exit 0
}

$owner = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($owner) {
    Write-Output "port $Port is held by PID $($owner.OwningProcess) but $Health does not answer; stop that process first"
    exit 1
}

$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    Write-Output "missing $Python; create the virtual environment first"
    exit 1
}

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
$process = Start-Process -FilePath $Python -ArgumentList '-m', 'src.server', '--headed', '--port', $Port `
    -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $DataDir 'server.out.log') `
    -RedirectStandardError (Join-Path $DataDir 'server.err.log')
Set-Content -Path $PidFile -Value $process.Id -Encoding ascii

for ($i = 0; $i -lt 60; $i++) {
    if (Test-Health) {
        Write-Output "server started on port $Port (PID $($process.Id))"
        exit 0
    }
    if ($process.HasExited) { break }
    Start-Sleep -Seconds 1
}
Write-Output "server did not answer $Health within 60 s; see $(Join-Path $DataDir 'server.err.log')"
exit 1
