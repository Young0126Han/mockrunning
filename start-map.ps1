$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Project Python environment is missing.' }
$url = 'http://127.0.0.1:8765'
$ready = $false
try {
    $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2
    if ($health.app -eq 'ios-location-controller' -and $health.version -eq '2.0') { $ready = $true }
} catch {}
if (-not $ready) {
    $listener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
    if ($listener) { throw 'Port 8765 is occupied by another or older server.' }
    Start-Process -FilePath $python -ArgumentList '-m','ios_location_controller.web' -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root 'server.stdout.log') -RedirectStandardError (Join-Path $root 'server.stderr.log')
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 300
        try {
            $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 1
            if ($health.version -eq '2.0') { $ready = $true; break }
        } catch {}
    }
}
if (-not $ready) { throw 'Server failed to start; see server.stderr.log.' }
Start-Process "$url/?v=2"
Write-Output "Route Studio ready: $url"
