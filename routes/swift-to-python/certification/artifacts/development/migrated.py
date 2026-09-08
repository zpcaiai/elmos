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


def _elmos_checked_add(left: int, right: int) -> int:
    return _elmos_in_range(left + right)


def calculate(subtotal: int, tax: int) -> int:
    _elmos_in_range(subtotal)
    _elmos_in_range(tax)
    if (subtotal < 0):
        return 0
    return _elmos_checked_add(subtotal, tax)
