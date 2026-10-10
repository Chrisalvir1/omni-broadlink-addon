from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, Mock

from src.broadlink_manager import BroadlinkManager


def _manager(tmp_path):
    return BroadlinkManager(storage_path=str(tmp_path / "remotes.json"))


def test_device_commands_reuse_discovered_object_and_serialize(tmp_path):
    manager = _manager(tmp_path)
    ip = "192.0.2.10"
    device = Mock()
    device.host = (ip, 80)
    manager._device_instances[ip] = device
    manager.scan_devices = AsyncMock(return_value={})
    active = 0
    maximum_active = 0

    def send(_data):
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        time.sleep(0.03)
        active -= 1

    device.send_data.side_effect = send
    async def run_both():
        return await asyncio.gather(
            manager.send_command(ip, "cG93ZXIx"),
            manager.send_command(ip, "cG93ZXIy"),
        )

    result = asyncio.run(run_both())
    assert result == [True, True]
    assert device.send_data.call_count == 2
    assert maximum_active == 1


def test_missing_cached_device_triggers_fresh_discovery(tmp_path):
    manager = _manager(tmp_path)
    manager.scan_devices = AsyncMock(return_value={})
    assert asyncio.run(manager.send_command("192.0.2.11", "cG93ZXI=")) is False
    manager.scan_devices.assert_awaited_once_with(force=True)


def test_timed_out_command_invalidates_stale_connection_without_logging_payload(tmp_path, caplog):
    manager = _manager(tmp_path)
    ip = "192.0.2.12"
    device = Mock()
    device.host = (ip, 80)
    device.send_data.side_effect = lambda _data: time.sleep(0.05)
    manager._device_instances[ip] = device
    manager.discovered_devices[ip] = {"ip": ip}
    manager._command_timeout = 0.005

    assert asyncio.run(manager.send_command(ip, "c2VjcmV0")) is False
    assert ip not in manager._device_instances
    assert ip not in manager.discovered_devices
    assert "c2VjcmV0" not in caplog.text


def test_timeout_keeps_device_serialized_until_blocking_call_finishes(tmp_path):
    manager = _manager(tmp_path)
    ip = "192.0.2.13"
    device = Mock()
    device.host = (ip, 80)
    manager._device_instances[ip] = device
    manager.scan_devices = AsyncMock(return_value={})
    started = __import__("threading").Event()
    release = __import__("threading").Event()
    calls = 0

    def send(_data):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            release.wait(1)

    device.send_data.side_effect = send
    manager._command_timeout = 0.01

    async def run():
        first = asyncio.create_task(manager.send_command(ip, "cG93ZXIx"))
        await asyncio.to_thread(started.wait, 1)
        second = asyncio.create_task(manager.send_command(ip, "cG93ZXIy"))
        await asyncio.sleep(0.03)
        assert calls == 1
        release.set()
        return await asyncio.gather(first, second)

    assert asyncio.run(run()) == [False, False]
    assert calls == 1
