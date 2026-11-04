"""Exercise settings reads with a connected BLE client, without booting HA."""

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("homeassistant.core")

from custom_components.glance_clock.glance_pb2 import Settings


@pytest.fixture
def notification(monkeypatch):
    # The legacy platform base is irrelevant to the BLE read under test.
    legacy = types.ModuleType("homeassistant.components.notify.legacy")
    legacy.BaseNotificationService = object
    monkeypatch.setitem(sys.modules, legacy.__name__, legacy)
    path = Path(__file__).resolve().parents[1] / "custom_components/glance_clock/notify.py"
    spec = importlib.util.spec_from_file_location(
        "custom_components.glance_clock._notify_test", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client = SimpleNamespace(
        is_connected=True,
        connect=AsyncMock(side_effect=RuntimeError("Client is already connected")),
        read_gatt_char=AsyncMock(),
        services=Mock(),
    )
    manager = SimpleNamespace(
        is_connected=True, client=client,
        get_cached_settings=Mock(return_value=None), cache_settings=Mock(),
    )
    service = module.GlanceClockNotificationService({"connection_manager": manager})
    return service, manager, client


@pytest.mark.asyncio
async def test_settings_read_reuses_connection_and_caches_result(notification):
    service, manager, client = notification
    settings = Settings(nightModeEnabled=True, displayBrightness=42)
    client.read_gatt_char.return_value = settings.SerializeToString()
    result = await service.async_read_current_settings()
    assert result["nightModeEnabled"] is True
    assert result["displayBrightness"] == 42
    client.connect.assert_not_awaited()
    client.read_gatt_char.assert_awaited_once()
    manager.cache_settings.assert_called_once_with(result)


@pytest.mark.asyncio
async def test_failed_settings_read_returns_no_data(notification):
    service, manager, client = notification
    client.read_gatt_char.side_effect = RuntimeError("Disconnected")
    assert await service.async_read_current_settings() is None
    manager.cache_settings.assert_not_called()
