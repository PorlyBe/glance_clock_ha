import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from test_scenes import NOW, decode, event

from custom_components.glance_clock.apps.controller import AppController


class Connection:
    is_connected = True

    def __init__(self):
        self.send_command = AsyncMock(return_value=True)


@pytest.fixture
def controller():
    clock = Connection()
    return AppController(clock, lambda: NOW, asyncio.create_task)


@pytest.mark.asyncio
async def test_expired_calendar_clears_and_ended_meetings_do_not_return(controller):
    await controller.set_calendar([event(hour=12, end=13)])
    controller.now = lambda: NOW + timedelta(minutes=16)
    await controller.refresh()
    assert (
        len(
            decode(controller.connection.send_command.call_args.args[0])
            .object[0]
            .fill.segment
        )
        == 1
    )
    await controller.close()


@pytest.mark.asyncio
async def test_offline_rejects_and_reconnect_restores_only_calendar(controller):
    await controller.set_calendar([event()])
    controller.connection.is_connected = False
    with pytest.raises(ValueError, match="disconnected"):
        controller.announce(text="Score")
    controller.connection.is_connected = True
    await controller.refresh()
    assert all(
        o.method == 2
        for o in decode(controller.connection.send_command.call_args.args[0]).object
    )
    await controller.close()


@pytest.mark.asyncio
async def test_queue_order_calendar_update_does_not_interrupt_and_unload_cancels(
    controller, monkeypatch
):
    started, release = asyncio.Event(), asyncio.Event()

    async def sleep(_):
        started.set()
        await release.wait()

    monkeypatch.setattr(
        "custom_components.glance_clock.apps.controller.asyncio.sleep", sleep
    )
    await controller.set_calendar([event()])
    controller.announce(text="First", duration=3)
    controller.announce(text="Second", duration=3)
    await started.wait()
    count = controller.connection.send_command.call_count
    await controller.set_calendar([event("new", color=11)])
    assert controller.connection.send_command.call_count == count
    release.set()
    await controller._worker
    texts = [
        o.text[0].text
        for call in controller.connection.send_command.call_args_list
        if call.args[0][0] == 0
        for o in decode(call.args[0]).object
        if o.method == 4
    ]
    assert texts == [b"First", b"Second"]
    last = decode(controller.connection.send_command.call_args.args[0])
    assert last.object[0].fill.segment[1] >> 16 == 11
    release.clear()
    started.clear()
    controller.announce(text="Cancel", duration=3)
    await started.wait()
    count = controller.connection.send_command.call_count
    await controller.close()
    assert controller.connection.send_command.call_count == count
    assert controller._worker.done()


@pytest.mark.asyncio
async def test_queue_bounded_and_expired_announcements_skipped(controller):
    for i in range(8):
        controller.announce(text=str(i))
    with pytest.raises(ValueError, match="full"):
        controller.announce(text="overflow")
    controller.now = lambda: NOW + timedelta(seconds=61)
    await controller._worker
    controller.connection.send_command.assert_not_awaited()
    await controller.close()


@pytest.mark.asyncio
async def test_failed_write_not_replayed_and_next_request_can_run(controller):
    controller.connection.send_command.return_value = False
    controller.announce(text="one", sound=6)
    await controller._worker
    assert (
        controller.connection.send_command.call_count == 2
    )  # attempt + silent restore
    await controller.close()


@pytest.mark.asyncio
async def test_round_robin_only_visible_events(controller):
    await controller.set_calendar([event("a"), event("b", color=11)])
    assert [controller.next_meeting().key for _ in range(3)] == ["a", "b", "a"]
    await controller.close()


@pytest.mark.asyncio
async def test_notice_slot_deleted_before_ring_only_restore(controller, monkeypatch):
    async def no_wait(_):
        return

    monkeypatch.setattr(
        "custom_components.glance_clock.apps.controller.asyncio.sleep", no_wait
    )
    await controller.set_calendar([event()])
    controller.connection.send_command.reset_mock()
    controller.announce(text="Meeting reminder", duration=3, sound=6)
    await controller._worker
    packets = [call.args[0] for call in controller.connection.send_command.call_args_list]
    assert packets[0][:4] == bytes([0, 0, 24, 7])
    assert packets[1] == bytes([33, 0, 0, 7])
    assert packets[2][:4] == bytes([0, 0, 8, 7])
    assert all(o.method == 2 for o in decode(packets[2]).object)
    controller.connection.send_command.reset_mock()
    await controller.refresh()
    assert controller.connection.send_command.call_count == 1
    await controller.close()


@pytest.mark.asyncio
async def test_failed_scene_delete_retried_without_replaying_notice(controller):
    controller.connection.send_command.side_effect = [False, True, True]
    await controller.set_calendar([event()])
    await controller.refresh()
    packets = [call.args[0] for call in controller.connection.send_command.call_args_list]
    assert packets[:2] == [bytes([33, 0, 0, 7])] * 2
    assert packets[2][:4] == bytes([0, 0, 8, 7])
    await controller.close()


@pytest.mark.asyncio
async def test_reconnect_cleans_notice_even_without_calendar(controller, monkeypatch):
    async def disconnect_during_notice(_):
        controller.connection.is_connected = False

    monkeypatch.setattr(
        "custom_components.glance_clock.apps.controller.asyncio.sleep",
        disconnect_during_notice,
    )
    controller.announce(text="Meeting reminder", duration=3)
    await controller._worker
    assert controller.connection.send_command.call_count == 1
    controller.connection.is_connected = True
    await controller.refresh()
    packets = [call.args[0] for call in controller.connection.send_command.call_args_list]
    assert packets[1] == bytes([33, 0, 0, 7])
    assert packets[2][:4] == bytes([0, 0, 8, 7])
    controller.connection.send_command.reset_mock()
    await controller.refresh()
    controller.connection.send_command.assert_not_awaited()
    await controller.close()
