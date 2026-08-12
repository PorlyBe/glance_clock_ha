"""Resolving the firmware's enum names to the bytes it expects.

The clock's protobuf fields are integers, and every service takes friendly
names for them. Turning one into the other used to be `TABLE.get(name,
default)` in some places and a raising lookup in others, so the same typo
either failed loudly or quietly produced white, silence, or a pulse. This is
the raising version, in one place.
"""

from __future__ import annotations


def lookup_enum(table: dict[str, int], value, what: str) -> int:
    """Resolve a name from one of the enum tables, or pass an index through.

    Names are stripped and lowercased first, so a value out of a template that
    kept its indentation still resolves. An unknown name raises with the whole
    list of valid ones, because the alternative -- a silent default -- is
    indistinguishable from the clock ignoring the command.
    """
    if isinstance(value, str):
        key = value.strip().lower()
        if key not in table:
            raise ValueError(
                f"unknown {what} '{value}'; expected one of {', '.join(sorted(table))}"
            )
        return table[key]
    return int(value)
