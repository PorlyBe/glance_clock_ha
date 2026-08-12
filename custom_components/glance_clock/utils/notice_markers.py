"""Inline markers that let a plain string carry a notice's settings.

The modern notify entity is deliberately minimal: `notify.send_message` takes a
message and a title and nothing else. That is the right shape for a phone and a
poor fit for a clock that can pick a sound, an animation and a colour.

Overloading `title` to mean "sound" was considered and rejected. A Home
Assistant with eight notify entities will sooner or later put the clock in a
generic list -- a script looping over notify targets, a blueprint taking a set
of them -- and something will send a real title. It would fail, or worse, do
nothing quietly.

So the settings ride in the message instead, in the same square-bracket idiom
the display text already uses for `[icon:130]`:

    "PAKET HAR KOMMIT [sound:bells] [anim:pulse] [color:dark_orange]"

Anything not recognised is left in the text untouched, so a message that merely
looks like a marker still arrives whole. `[icon:...]` is deliberately not
handled here -- it belongs to the display encoder further down.
"""

from __future__ import annotations

import re

#: Marker name -> the send_notice field it sets. Several spellings map to the
#: same field because people reach for different words for the same thing.
MARKERS = {
    "sound": "sound",
    "anim": "animation",
    "animation": "animation",
    "effect": "animation",
    "color": "color",
    "colour": "color",
    "priority": "priority",
}

_PATTERN = re.compile(r"\[(\w+):([^\]]*)\]")


def extract_notice_options(text: str) -> tuple[str, dict]:
    """Pull recognised markers out of a message.

    Returns the text with those markers removed, and the options they set.
    The values are not validated here -- send_notice resolves them and raises
    with the full list of what would have worked, which is a better error than
    anything this could produce.
    """
    options: dict = {}

    def _take(match: re.Match) -> str:
        name = match.group(1).strip().lower()
        field = MARKERS.get(name)
        if field is None:
            # Not ours: [icon:130] and anything unrecognised stay in the text.
            return match.group(0)
        options[field] = match.group(2).strip()
        return ""

    cleaned = _PATTERN.sub(_take, text)

    # Removing a marker from the middle of a sentence leaves a double space,
    # and the display font has no way to make that look deliberate.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()

    return cleaned, options
