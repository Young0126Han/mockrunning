# iOS Location Controller

Windows Python controller for location simulation on an owned or test iPhone.

This project wraps `pymobiledevice3` and GPX playback. It is intended for testing apps you own. It does not attempt to bypass third-party app verification.

## Requirements

- Windows 10/11
- Python 3.11+
- Apple Mobile Device Support (installing iTunes from Apple installs the driver)
- A paired iPhone with Developer Mode enabled
- `pymobiledevice3`

## Setup

```powershell
cd D:\ios-location-controller
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .
```

For iOS 17.4 and newer, the controller automatically creates an in-process userspace RSD tunnel
over USB. No elevated tunnel command is required. For older iOS versions, the controller falls
back to USB lockdown mode.

If an external tool needs a persistent, kernel-routable tunnel, start it in an elevated PowerShell
terminal over the USB cable:

```powershell
python -m pymobiledevice3 remote start-tunnel
```

The web playback console uses the tunnel when `IOS_RSD_HOST` and `IOS_RSD_PORT`
are set before starting the map server:

```powershell
$env:IOS_RSD_HOST = "<host>"
$env:IOS_RSD_PORT = "<port>"
python -m ios_location_controller map
```

The command prints an RSD host and port. Pass them to this controller:

```powershell
python -m ios_location_controller play .\routes\sample.gpx --speed-kmh 5 --interval 1 --rsd-host <host> --rsd-port <port>
```

For older iOS versions, USB lockdown mode needs no RSD arguments:

```powershell
python -m ios_location_controller play .\routes\sample.gpx --speed-kmh 5
```

## Commands

```powershell
python -m ios_location_controller list
python -m ios_location_controller validate .\routes\sample.gpx
python -m ios_location_controller play .\routes\sample.gpx --speed-kmh 5 --loop
python -m ios_location_controller clear

Start the local OpenStreetMap route editor:

    python -m ios_location_controller map

Open http://127.0.0.1:8765 in a browser, click the map to add points, then export `route.gpx`.

The map uses Leaflet from the unpkg CDN and OpenStreetMap tiles, so an internet connection is required while viewing the map.
```

The controller attempts to clear simulated location on normal exit, `Ctrl+C`, and playback errors.
