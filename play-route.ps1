param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Route,
    [Parameter(Mandatory = $true)]
    [ValidateRange(0.01, 10000)]
    [double] $SpeedKmh,
    [double] $Interval = 1.0,
    [string] $Udid,
    [string] $RsdHost,
    [int] $RsdPort,
    [switch] $Loop
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python.exe -ErrorAction Stop).Source
}
$env:PYTHONPATH = Join-Path $root 'src'
$args = @('-m', 'ios_location_controller', 'play', $Route, '--speed-kmh', $SpeedKmh, '--interval', $Interval)
if ($Udid) { $args += @('--udid', $Udid) }
if ($RsdHost) { $args += @('--rsd-host', $RsdHost, '--rsd-port', $RsdPort) }
if ($Loop) { $args += '--loop' }
& $python @args
exit $LASTEXITCODE
