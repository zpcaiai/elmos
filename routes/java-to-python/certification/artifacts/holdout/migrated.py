from __future__ import annotations


_ELMOS_INTEGER_MIN = -(2 ** 63)
_ELMOS_INTEGER_MAX = 2 ** 63 - 1


def _elmos_in_range(value: int) -> int:
    """Canonical `integer` is a 64-bit signed integer (rule R1).

    Python's int is arbitrary precision, so a result no other target
    can hold has to be rejected here rather than silently succeed.
    """
    if not _ELMOS_INTEGER_MIN <= value <= _ELMOS_INTEGER_MAX:
        raise OverflowError("ELMOS_INTEGER_OVERFLOW")
    return value


def clamp(value: int, upper: int) -> int:
    _elmos_in_range(value)
    _elmos_in_range(upper)
    if (value > upper):
        return upper
    if (value < 0):
        return 0
    return value
