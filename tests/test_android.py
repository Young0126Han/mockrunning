import asyncio
from unittest.mock import AsyncMock

import pytest

from ios_location_controller import android
from ios_location_controller.connections import create_device
from ios_location_controller.gpx import Point


@pytest.mark.parametrize('value', ['host;id:5555', '127.0.0.1:0', '127.0.0.1:65536',
                                 '0.0.0.0:5555', '-s', None, '127.0.0.1:1.5'])
def test_bad_endpoint(value):
    with pytest.raises(ValueError):
        android.endpoint(value)


def test_ipv6_and_device_factory():
    assert android.endpoint('[fd00::1]:1234') == '[fd00::1]:1234'
    assert isinstance(create_device('android'), android.AndroidDevice)
    device = create_device(rsd_host='fd00::1', rsd_port=1234)
    assert device.rsd_port == 1234
    for options in [{'platform': 'other'}, {'rsd_host': '127.0.0.1'},
                    {'platform': 'android', 'rsd_port': 1234}, {'address': '127.0.0.1:5555'}]:
        with pytest.raises(ValueError):
            create_device(**options)


def test_pair_code_is_stdin(monkeypatch):
    command = AsyncMock()
    monkeypatch.setattr(android, 'adb', command)
    asyncio.run(android.pair('192.168.1.2:12345', '123456'))
    command.assert_awaited_once_with('pair', '192.168.1.2:12345', input_text='123456\n')
    with pytest.raises(ValueError):
        asyncio.run(android.pair('192.168.1.2:12345', 'bad;code'))


def test_discovery(monkeypatch):
    monkeypatch.setattr(android, 'adb', AsyncMock(return_value=
        'List of devices attached\nusb123 device product:test\n192.168.1.2:5555 offline\nabc unauthorized\n'))
    result = asyncio.run(android.discover())
    assert len(result) == 3
    assert result[0]['platform'] == 'android'
    assert result[2]['type'] == 'ADB / unauthorized'


def test_android_lifecycle(monkeypatch):
    calls = []

    async def command(*args, **kwargs):
        calls.append(args)
        if args[-1] == 'get-state':
            return 'device'
        if args[-1] == 'help':
            return 'set-test-provider-location'
        if args[-1] == 'is-location-enabled':
            return 'true'
        if 'get' in args:
            return 'MOCK_LOCATION: ignore'
        return ''

    monkeypatch.setattr(android, 'adb', command)

    async def scenario():
        device = android.AndroidDevice(address='192.168.1.2:5555')
        await device.connect()
        await device.set_point(Point(31, 121))
        assert device.providers == ['gps', 'network']
        await device.clear()
        assert device.providers == []
        await device.set_point(Point(32, 122))
        await device.close()
        assert device.original_mode is None
        assert calls[-1][-5:] == ('appops', 'set', 'com.android.shell', 'android:mock_location', 'ignore')
    asyncio.run(scenario())
    assert calls[0] == ('connect', '192.168.1.2:5555')
    assert any('31.00000000,121.00000000' in call for call in calls)


def test_failed_cleanup_is_retryable():
    async def scenario():
        device = android.AndroidDevice('abc')
        device.providers = ['gps', 'network']
        device.original_mode = 'default'
        device.shell = AsyncMock(side_effect=[RuntimeError('offline'), ''])
        with pytest.raises(RuntimeError, match='cleanup failed'):
            await device.close()
        assert device.providers == ['gps']
        assert device.original_mode == 'default'
        device.shell = AsyncMock(return_value='')
        await device.close()
        assert not device.providers
        assert device.original_mode is None
    asyncio.run(scenario())


def test_explicit_recovery_clears_existing_providers():
    async def scenario():
        device = android.AndroidDevice('abc')
        device.shell = AsyncMock(return_value='')
        await device.clear(existing=True)
        assert device.shell.await_count == 2
        assert device.providers == []
    asyncio.run(scenario())


def test_unsupported_rom_does_not_change_permissions(monkeypatch):
    monkeypatch.setattr(android, 'adb', AsyncMock(return_value='device'))
    device = android.AndroidDevice('abc')
    device.shell = AsyncMock(return_value='old help')
    with pytest.raises(RuntimeError, match='lacks ADB'):
        asyncio.run(device.connect())
    assert device.original_mode is None
    assert device.shell.await_count == 1


def test_cli_android_options():
    from ios_location_controller.cli import build_parser
    args = build_parser().parse_args(['play', 'route.gpx', '--platform', 'android',
                                     '--address', '192.168.1.2:5555'])
    assert args.platform == 'android'
    assert args.address == '192.168.1.2:5555'


LOCATION_HELP = 'Location service commands:\n  providers\n    set-test-provider-location <PROVIDER>\n'


@pytest.mark.parametrize('returncode', [0, -1, 255])
@pytest.mark.parametrize('supported', [True, False])
def test_connect_accepts_normal_nonzero_location_help(monkeypatch, returncode, supported):
    calls = []
    help_text = LOCATION_HELP if supported else 'Location service commands:\n  help\n'

    async def subprocess(*args, **kwargs):
        calls.append(args)
        code, output = 0, ''
        if args[-1] == 'get-state':
            output = 'device'
        elif args[-3:] == ('cmd', 'location', 'help'):
            code, output = returncode, help_text
        elif args[-1] == 'is-location-enabled':
            output = 'true'
        elif args[-4:] == ('appops', 'get', 'com.android.shell', 'android:mock_location'):
            output = 'MOCK_LOCATION: ignore'
        return type('Process', (), {
            'returncode': code,
            'communicate': AsyncMock(return_value=(output.encode(), b'')),
        })()

    monkeypatch.setenv('ADB_PATH', 'adb')
    monkeypatch.setattr(android.asyncio, 'create_subprocess_exec', subprocess)
    device = android.AndroidDevice('abc')
    if supported:
        asyncio.run(device.connect())
        assert device.original_mode == 'ignore'
    else:
        with pytest.raises(RuntimeError, match='lacks ADB test-provider support'):
            asyncio.run(device.connect())
        assert device.original_mode is None
        assert not any('appops' in call for call in calls)


@pytest.mark.parametrize('command, returncode, stdout, stderr', [
    (('cmd', 'location', 'help'), 1, LOCATION_HELP, ''),
    (('cmd', 'location', 'help'), 255, 'Unknown command: location', ''),
    (('cmd', 'location', 'help'), 255, '', ''),
    (('cmd', 'location', 'help'), 255, LOCATION_HELP, 'error: device unauthorized'),
    (('cmd', 'location', 'help'), 255, LOCATION_HELP, 'Permission denied'),
    (('cmd', 'location', 'help'), 0, '', 'SecurityException: permission denied'),
    (('cmd', 'location', 'help'), 255, LOCATION_HELP + 'Exception occurred', ''),
    (('cmd', 'location', 'providers', 'add-test-provider', 'gps'), 255, LOCATION_HELP, ''),
])
def test_adb_help_exception_does_not_hide_failures(monkeypatch, command, returncode, stdout, stderr):
    process = type('Process', (), {
        'returncode': returncode,
        'communicate': AsyncMock(return_value=(stdout.encode(), stderr.encode())),
    })()
    monkeypatch.setenv('ADB_PATH', 'adb')
    monkeypatch.setattr(android.asyncio, 'create_subprocess_exec', AsyncMock(return_value=process))
    with pytest.raises(RuntimeError):
        asyncio.run(android.adb('-s', 'abc', 'shell', *command))


def test_adb_subprocess_cancellation(monkeypatch):
    class Process:
        returncode = None
        killed = False

        async def communicate(self, data=None):
            if not self.killed:
                await asyncio.sleep(100)
            return b'', b''

        def kill(self):
            self.killed = True

    process = Process()
    monkeypatch.setattr(android.shutil, 'which', lambda _: 'adb')
    monkeypatch.setattr(android.asyncio, 'create_subprocess_exec', AsyncMock(return_value=process))

    async def scenario():
        task = asyncio.create_task(android.adb('devices'))
        await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert process.killed
    asyncio.run(scenario())
