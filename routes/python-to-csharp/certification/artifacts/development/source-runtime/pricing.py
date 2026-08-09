def calculate(subtotal: int, tax: int) -> int:
    if subtotal < 0:
        return 0
    return subtotal + tax
