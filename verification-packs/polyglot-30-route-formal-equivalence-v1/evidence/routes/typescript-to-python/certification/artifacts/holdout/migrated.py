from __future__ import annotations


def clamp(value: float, upper: float) -> float:
    if (value > upper):
        return upper
    if (value < 0):
        return 0
    return value
