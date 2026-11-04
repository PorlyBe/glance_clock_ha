# Calendar wedges and reminders

Display the next twelve hours from Home Assistant `calendar.*` entities. Google
Calendar authentication stays in Home Assistant's existing Google Calendar
integration; other HA calendar providers work too. No additional Google OAuth
client, server, webhook or external account is required by Glance.

## Setup

1. Set up this Glance integration and its Bluetooth connection as described in
   the main README. Physical hand synchronization still requires a Bluetooth
   Current Time Service; the calendar renderer does not set the hands.
2. Add [Google Calendar](https://www.home-assistant.io/integrations/google/) or
   another [HA calendar provider](https://www.home-assistant.io/integrations/calendar/).
3. In **Developer tools → Actions**, call `glance_clock.show_calendar` with a
   mapping from your calendar entity IDs to colors:

```yaml
action: glance_clock.show_calendar
data:
  calendars:
    calendar.personal: blue
    calendar.family: blue_violet
    calendar.work: dark_orange
```

Replace these example entity IDs with your own. This uses `calendar.get_events`
so overlapping events are included, rather than reading only the next event
from the entity's state attributes. All-day and cancelled events are omitted;
ended events and events beyond the next twelve hours are not drawn.

For multiple clocks, pass `entry_id` to each action. This is the integration
configuration entry ID, not the device MAC or entity ID. Find it in **Developer
tools → Template** using `{{ config_entry_id('light.YOUR_CLOCK_LIGHT') }}`.
Omit it when only one clock is configured.

## Wedges and refresh

The clock has 48 quarter-hour columns and four bands. A single event fills all
four bands. Overlaps share the bands: two events get 2+2; three get 2+1+1; four
get 1+1+1+1. Earlier events occupy the outer bands. A fifth simultaneous event
cannot be displayed; a warning reports the hidden count. Geometry uses HA's
local timezone, including midnight and DST transitions. During a repeated DST
hour, the nearer occurrence takes precedence at the shared clock positions.

Copy `blueprints/automation/glance_clock/calendar.yaml` to HA's matching
`config/blueprints/automation/glance_clock/` directory and create an automation
from it. It refreshes every five minutes and at HA startup. The in-memory
calendar is redrawn every minute to remove ended events. If fetching fails for
more than fifteen minutes, wedges clear to avoid displaying stale data. The
automation repopulates the calendar after HA restarts.

To clear the calendar, disable its refresh automation and call `show_calendar`
with `calendars: {}`. Disabling the automation alone lets the cached display
expire after fifteen minutes.

Colors accept names from the integration palette or integer IDs 1–53. Useful
IDs include gold 1, orange 2, red 5, purple 11, white 12, blue 15, light blue 16,
light green 21 and dark green 22. These are fixed palette colors, not RGB.

## Scrolling meeting reminders

```yaml
action: glance_clock.announce_calendar
data:
  effect: breathing
  duration: 12
  sound: none
```

Each call rotates to the next visible meeting. Text and the wedge cue start
together. Available cues are `none`, `breathing`, `breath_1`, `breath_2`,
`dim_once` and `dim_twice`. The breathing/pulse effect is the clock firmware's
pixel animation, not a calibrated smooth brightness dimmer. Text may repeat
within the display duration. Names are transliterated and limited to 64 ASCII
bytes; select a duration of 3–30 seconds appropriate to their length.

Use `blueprints/automation/glance_clock/scheduled_app.yaml` to choose an
interval or comma-separated local times such as `08:00, 12:30, 18:00` and select
this action in its action picker. Intervals align to midnight. A repeated DST
hour can repeat a time-of-day announcement.

For advance alerts, create HA calendar triggers with offsets. Multiple triggers
allow reminders at several times before the same meeting:

```yaml
alias: Glance meeting alerts
triggers:
  - trigger: calendar
    entity_id: calendar.work
    event: start
    offset: '-00:05:00'
  - trigger: calendar
    entity_id: calendar.work
    event: start
    offset: '00:00:00'
actions:
  - action: glance_clock.announce
    data:
      text: '{{ trigger.calendar_event.summary }}'
      duration: 12
      sound: rise
      effect: glow
      primary_color: 15
      secondary_color: 12
mode: queued
```

Custom alerts support `none`, `glow` or `wave`, with two configurable palette
colors. They use a ring cue rather than targeting the specific event's wedge.
Google calendars generally poll every fifteen minutes, so create test events
sufficiently far ahead.

## Display behavior and limitations

Calendar reminders and custom announcements share a bounded queue of eight
waiting items. Announcements expire after sixty seconds and are not replayed
after reconnecting. Calendar refreshes wait for the current announcement; the
current calendar returns afterward. Cleanup is retried if a write or reconnect
fails. All BLE writes use the integration's existing connection and write lock.

Legacy notice/timer/forecast actions remain separate from this queue. Avoid
mixing their persistent scenes with the calendar because firmware scene
priorities can hide it. Highly fragmented calendars can exceed the 512-byte
BLE scene limit; these are rejected before replacing the last usable scene.

Setup uses HA actions and automation blueprints, not a new options-flow screen.
Calendar wedges, shared overlap bands, scrolling, breathing and restoration
have been observed on a physical clock (firmware 1.4.47, HA Core 2026.10.1).
This does not establish compatibility with every clock/adapter or long-term
Bluetooth reliability. Google authentication is provided and maintained by HA.

## Tests

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest -q
```

Pure tests cover geometry, DST, protobuf bounds, queue expiration, failed writes
and scene restoration. HA-dependent service/settings tests additionally run
when Home Assistant is installed; otherwise pytest reports those modules as
skipped. No physical clock is required for the automated tests.
