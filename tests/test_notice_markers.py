"""Markers that let `notify.send_message` carry a notice's settings.

The modern notify entity takes a message and a title and nothing else --
confirmed against Home Assistant 2026.8.1, where `notify.send_message` has
exactly those two fields. Overloading `title` to mean "sound" was rejected: an
instance with eight notify entities will put the clock in a generic list sooner
or later, and something will send a real title.

So the settings ride in the message, in the same bracket idiom the display text
already uses for [icon:130].
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "glance_clock"


def _load():
    package = types.ModuleType("_gm")
    package.__path__ = [str(COMPONENT)]
    sys.modules["_gm"] = package
    utils = types.ModuleType("_gm.utils")
    utils.__path__ = [str(COMPONENT / "utils")]
    sys.modules["_gm.utils"] = utils

    spec = importlib.util.spec_from_file_location(
        "_gm.utils.notice_markers", COMPONENT / "utils" / "notice_markers.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_gm.utils.notice_markers"] = module
    spec.loader.exec_module(module)
    return module


markers = _load()
extract = markers.extract_notice_options


def test_a_plain_message_is_left_alone():
    # The common case, and the one a generic notify sender produces.
    assert extract("PAKET HAR KOMMIT") == ("PAKET HAR KOMMIT", {})


def test_a_marker_sets_its_option_and_leaves_the_text():
    text, options = extract("KLART [sound:bells]")
    assert text == "KLART"
    assert options == {"sound": "bells"}


def test_several_markers_all_apply():
    text, options = extract("POST [sound:hello] [anim:pulse] [color:dark_orange]")
    assert text == "POST"
    assert options == {"sound": "hello", "animation": "pulse", "color": "dark_orange"}


@pytest.mark.parametrize(
    "spelling, field",
    [
        ("anim", "animation"),
        ("animation", "animation"),
        ("effect", "animation"),
        ("color", "color"),
        ("colour", "color"),
    ],
)
def test_the_spellings_people_reach_for_all_work(spelling, field):
    _, options = extract(f"X [{spelling}:pulse]")
    assert field in options


def test_icon_markers_are_left_for_the_display_encoder():
    # [icon:...] is handled further down, when the text becomes bytes. Eating
    # it here would silently drop every glyph in the integration's own docs.
    text, options = extract("HEJ [icon:134]")
    assert text == "HEJ [icon:134]"
    assert options == {}


def test_an_unrecognised_marker_stays_in_the_message():
    # A message that merely looks like a marker still arrives whole.
    text, options = extract("SE [ref:12] NU")
    assert text == "SE [ref:12] NU"
    assert options == {}


def test_a_marker_pulled_from_the_middle_does_not_leave_a_gap():
    # The display font cannot make a double space look deliberate.
    text, _ = extract("KAFFE [sound:bells] AR KLART")
    assert text == "KAFFE AR KLART"


def test_marker_names_and_values_are_case_and_space_tolerant():
    # The name is matched case-insensitively and the value is stripped. The
    # value's own case is left alone -- send_notice lowercases it when it
    # resolves, and doing it twice would hide where it happened.
    _, options = extract("X [SOUND: Bells ]")
    assert options == {"sound": "Bells"}


def test_values_are_not_validated_here():
    # send_notice resolves them and raises with the whole palette, which is a
    # better error than this could produce.
    _, options = extract("X [color:chartreuse]")
    assert options == {"color": "chartreuse"}
