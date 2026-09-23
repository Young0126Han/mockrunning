$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $root 'src'
$python = (Get-Command python.exe -ErrorAction Stop).Source
$stdout = Join-Path $root 'server.stdout.log'
$stderr = Join-Path $root 'server.stderr.log'
Start-Process -FilePath $python -ArgumentList '-m', 'ios_location_controller.web' -WorkingDirectory $root -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Start-Sleep -Seconds 3
try {
    Invoke-WebRequest 'http://127.0.0.1:8765' -UseBasicParsing -TimeoutSec 2 | Out-Null
    Start-Process 'http://127.0.0.1:8765'
} catch {
    Write-Host "Map server failed to start. See $stderr"
    if (Test-Path $stderr) { Get-Content $stderr }
    exit 1
}
