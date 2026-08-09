from __future__ import annotations


def calculate(subtotal: float, tax: float) -> float:
    if (subtotal < 0):
        return 0
    return (subtotal + tax)
