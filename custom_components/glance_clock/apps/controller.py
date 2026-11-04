"""One calendar base and a bounded, expiring announcement queue per clock."""

import asyncio
import logging
from collections import deque
from datetime import timedelta

from .scenes import calendar_segments, scene_packet

_LOGGER = logging.getLogger(__name__)


class AppController:
    def __init__(self, connection, now, create_task):
        self.connection = connection
        self.now = now
        self.create_task = create_task
        self.meetings = None
        self.fetched_at = None
        self.hidden = 0
        self._lock = asyncio.Lock()
        self._queue = deque()
        self._worker = None
        self._closed = False
        self._announcement_index = 0
        # A ring-only scene does not remove the firmware's previous text scene.
        # Also clean up our slot after a reload, when its old contents are unknown.
        self._needs_scene_delete = True

    def segments(self):
        if self.fetched_at is None or self.now() - self.fetched_at > timedelta(
            minutes=15
        ):
            return []
        segments, self.hidden = calendar_segments(self.meetings or [], self.now())
        return segments

    async def set_calendar(self, meetings):
        # Reject oversized calendars before replacing the last usable scene.
        scene_packet(calendar_segments(meetings, self.now())[0])
        self.meetings, self.fetched_at = meetings, self.now()
        await self.refresh()

    async def refresh(self, *_):
        if (
            self._closed
            or (self.meetings is None and not self._needs_scene_delete)
            or self._lock.locked()
        ):
            return
        async with self._lock:
            await self._restore()

    async def _restore(self):
        if not self._closed and self.connection.is_connected:
            if self._needs_scene_delete:
                if not await self.connection.send_command(bytes([33, 0, 0, 7])):
                    return
                self._needs_scene_delete = False
            await self.connection.send_command(scene_packet(self.segments()))

    def next_meeting(self):
        visible = {s.meeting for s in self.segments()}
        meetings = sorted(
            (m for m in self.meetings or [] if m.key in visible),
            key=lambda m: (m.start.timestamp(), m.key),
        )
        if not meetings:
            return None
        meeting = meetings[self._announcement_index % len(meetings)]
        self._announcement_index += 1
        return meeting

    def announce(self, **announcement):
        if self._closed or not self.connection.is_connected:
            raise ValueError(
                "Clock is disconnected; announcements are not replayed on reconnect"
            )
        if len(self._queue) >= 8:
            raise ValueError("Clock announcement queue is full")
        scene_packet(self.segments(), **announcement)
        self._queue.append((self.now() + timedelta(seconds=60), announcement))
        if self._worker is None or self._worker.done():
            self._worker = self.create_task(self._run())

    async def _run(self):
        while self._queue and not self._closed:
            expires, announcement = self._queue.popleft()
            if self.now() >= expires or not self.connection.is_connected:
                continue
            async with self._lock:
                try:
                    # Recompute base so finished meetings cannot return after an announcement.
                    packet = scene_packet(self.segments(), **announcement)
                    # Even an ambiguous/failed write may have reached the clock.
                    self._needs_scene_delete = True
                    sent = await self.connection.send_command(packet)
                    if sent:
                        await asyncio.sleep(announcement.get("duration", 12))
                except (ValueError, OSError):
                    _LOGGER.warning("Clock app announcement could not be displayed")
                finally:
                    await self._restore()

    async def close(self):
        self._closed = True
        self._queue.clear()
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
