# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
### Fixed
- **Writing any setting erased the Do Not Disturb schedule.** `build_settings` rebuilt the
  Settings message from the handful of fields the schema models, silently dropping
  everything else the clock carries -- including the nested DND schedule and at least one
  undocumented field. Settings writes now patch the device's own bytes. Confirmed on
  hardware: before the fix, a write deleted fields 1 and 15 and invented field 13.
- **Two settings writes within a minute reverted each other.** The cache was filled on
  read but never updated on write, and `clear_settings_cache()` was called from nowhere,
  so the second write patched a stale copy.
- **`displayBrightness` is not a 0-100 percentage.** Only its low byte is the manual
  level; 0 hands control back to the ambient light sensor. Real hardware reported 2016768
  (0x1EC600), so treating the whole field as a level both misread the state and destroyed
  the upper bits on write -- observed leaving the rim points dark.
- **The forecast always wrote °C.** A Fahrenheit household got correctly converted values
  under the wrong letter. The unit now follows the weather entity, falling back to the
  system setting. The values needed no change: Home Assistant converts them before this
  integration sees them, so converting again would double-convert.

- **A notice with an unknown colour name did nothing at all.** The name was swallowed
  before anything reached the clock, and the service call reported success. Unknown
  colours, sounds and animations now fail with the list of accepted names.
- **A timer without `intervals` displayed nothing.** `countdown` is a lead-in delay, not
  the count, so a timer given only a countdown ran an empty timeline. It is now refused
  with an explanation.
- **Non-ASCII text was mangled** on its way to the clock.
- **Buttons stayed greyed out after a reconnect.** They do not poll, so availability was
  only re-evaluated when something else happened to write their state.

### Added
- `set_dnd_schedule` and `read_dnd_schedule`, plus **DND Start** and **DND End** number
  entities. The schedule lives on the clock and keeps working while Home Assistant is
  down, which is what made losing it to a settings write worth fixing first.
- **Direct control of the LED rings.** `set_leds` and `clear_leds` draw and remove
  coloured segments; `set_animation` runs the firmware's own patterns; `set_scene` reaches
  the rest of the scene object -- timelines, the three effects, weather particles, text
  and sounds. The ring geometry is 4 rings of 48 pixels with pixel 0 at twelve o'clock,
  so one hour is exactly 4 pixels.
- **Device page controls** for all of it: an animation, colour and effect picker with Run
  and Stop buttons, a slot slider, a sound audition button, a **Clear All Scenes** button,
  a Mute switch, and the two hand-calibration buttons.
- **A notify entity**, `notify.<clock>`, so the clock works with `notify.send_message`
  like any modern notification target. Sound, animation, effect, colour and priority ride
  along in the message as `[sound:bells]` markers rather than taking over `title`.

### Changed
- **Scenes appear the moment they are sent.** Every scene write is now followed by a
  playback start, which also means a new scene replaces one already in the slot instead of
  waiting for the engine's next pass. Filmed on hardware: the wait was about fifteen
  seconds before, and is gone.

### Documentation
- `send_forecast` writes to scene slot 1, and a scene stays in its slot and replays until
  cleared, so `clear_leds` with slot 1 removes it. This already worked; nothing said so.

## [1.2.0] - 2025-11-14
### Added
- Support for icons in notification text using `[icon:CODE]` syntax. See `ICONS.md` for available codes.
- New timer service: send timer scenes with intervals and final text, including icon support.
- Major code cleanup and refactor:
	- Moved service handlers to dedicated files under `services/`.
	- Moved color utilities to `utils/color_utils.py`.
	- Improved Bluetooth connection management and modularized code.
	- Updated and clarified documentation and service descriptions.

## [1.1.0] - 2025-11-11
### Added
- Calibration flow added to the integration.
- Placeholder for "Scene clear" added to integration

## [1.0.2]
### Added
- Updated readme to include Bluetooth CTS addon

## [1.0.1]
### Added
- Cleanup and HAC submission prep

## [1.0.0]
### Added
- Initial release.
