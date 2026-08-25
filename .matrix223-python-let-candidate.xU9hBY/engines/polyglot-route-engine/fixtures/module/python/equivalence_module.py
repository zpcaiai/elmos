def calculate(subtotal: int, tax: int) -> int:
    if subtotal < 0:
        return 0
    return subtotal + tax


def clamp(value: int, minimum: int, maximum: int) -> int:
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def difference(left: int, right: int) -> int:
    return left - right


def clampNumber(value: float, minimum: float, maximum: float) -> float:
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value


def both(left: bool, right: bool) -> bool:
    return left and right
