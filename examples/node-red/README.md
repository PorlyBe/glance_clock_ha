# Driving the clock from Node-RED

Everything the clock can do is a Home Assistant service call, so from Node-RED
it is a **call service** node with `glance_clock` as the domain. Nothing here
needs a custom node or a direct Bluetooth connection — Node-RED talks to Home
Assistant, and Home Assistant owns the clock.

The flows in this directory are meant to be read as much as imported. Each one
is short, and the interesting part is the payload rather than the wiring.

| File | What it does |
|---|---|
| `weather.json` | Turns a weather entity into snow, rain or fog on the rings |
| `espresso.json` | Watches a temperature sensor and says when the machine is ready |

Import with **Menu → Import** and paste the file contents. Both flows reference
entity ids you will need to change to your own.

## The two things worth knowing first

**A scene stays in its slot.** It does not vanish when its lifetime runs out —
it stays and replays until something clears the slot. Use `clear_leds` with the
same slot when you want it gone. This is the single most surprising thing about
the clock, and it will look like a bug the first time it happens.

**Notices are immediate, scenes are not.** A notice interrupts and shows at
once. A scene joins the display on the clock's own cycle, which can take up to
about fifteen seconds. If the thing you are announcing matters right now — a
timer finishing, a door opening — send a notice.

## Weather on the rings

`set_scene` has a `weather` step type. It is a particle effect, not a forecast
readout: snow falls, rain streaks, fog drifts. The clock draws it.

```yaml
service: glance_clock.set_scene
data:
  mode: watchface
  slot: 1
  steps:
    - type: weather
      condition: snow      # snow, rain or fog
      position: full       # full, upper or lower
      intensity: 7         # 0-10
      seconds: 30
```

The flow maps a weather entity's state onto that: `snowy` becomes snow,
`rainy` and `pouring` become rain, `fog` becomes fog, and anything else clears
the slot so the clock goes back to normal. Intensity rises with `pouring`.

Slot 1 is deliberate. It leaves slot 0 free for the animation buttons on the
device page, so weather and a manually run animation do not fight.

## The espresso machine

This is the case the clock is genuinely good at: a thing you are waiting for,
in a room you walk past, where you do not want to open an app to check.

The flow watches a temperature sensor and fires once when it crosses the ready
threshold — the `rbe` node matters here, or you get a notice every time the
sensor reports while hot.

```yaml
service: glance_clock.send_notice
data:
  text: "ESPRESSO [icon:130]"
  animation: pulse
  color: lime_green
  sound: bells
```

A notice takes an animation from its own list, which is not the same list as
the LED animations: `none`, `pulse`, `wave`, `fire`, `sun`, `wheel`, the
`flower` pair, `fan`, `cloud`, `thunderstorm`, and a set of `weather_*` icons.
`none` shows the text with no ring animation at all, which is what the Sound
Play button uses.

The `[icon:CODE]` syntax puts one of the clock's built-in glyphs inline; 130 is
the clock face. See `ICONS.md` in the repository root for the full list.

Text is drawn from a limited font. Swedish letters are transliterated -- `å`
and `ä` become `a`, `ö` becomes `o` -- and anything with no glyph at all is
replaced by a visible box rather than silently dropped, so a mangled string
looks wrong instead of looking fine.

### Cooling down again

The second half of the flow sends a notice when the machine drops back below
temperature. Leave it out if you find it chatty — it is there to show that a
notice is cheap and that the clock is fine being talked to often.

## Waiting for the clock to be free

`binary_sensor.<name>_busy` is true while a notice or scene is playing. The
clock reports this itself and pushes every change, so it is something to wait
on rather than guess at -- a notice sent while another one plays is not queued,
it is simply lost.

The usual shape is a **current state** node checking the sensor is `off`
before the call service node, with a short delay and a retry when it is not.
Its attributes carry `digital_clock` and the raw byte, if you want to know
whether the digital time is on screen.

## Sound

Sound only plays if the clock is not muted. There is a **Mute** switch on the
device page, and it is easy to forget: a muted clock plays nothing and reports
no error, which looks exactly like a broken sound argument.

## Errors

Bad values now fail loudly. A colour name that does not exist raises and shows
up in Node-RED as a failed service call rather than doing nothing at all. The
message lists the whole palette.

The palette has no plain `green`, `purple`, `orange` or `cyan`, but those names
are accepted as aliases for the nearest real colour. See the colour list in
`custom_components/glance_clock/const.py`.
