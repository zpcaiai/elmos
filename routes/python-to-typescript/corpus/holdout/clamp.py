def clamp(value: int, upper: int) -> int:
    if value > upper:
        return upper
    if value < 0:
        return 0
    return value
