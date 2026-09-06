"""Original educational fixture: nonnegative integer cents; no external effects."""
import json
import sys

def quote(amount_cents: int) -> dict:
    if type(amount_cents) is not int or not 0 <= amount_cents <= 1_000_000:
        raise ValueError("amount_cents must be an integer in [0, 1000000]")
    subtotal = amount_cents
    discount = subtotal // 10 if subtotal >= 10_000 else 0
    total = subtotal - discount  # EL-LW-BREAKPOINT
    return {"subtotal": subtotal, "discount": discount, "total": total}

if __name__ == "__main__":
    try:
        print(json.dumps(quote(json.loads(sys.argv[1]))))
    except (ValueError, TypeError, IndexError, json.JSONDecodeError):
        print(json.dumps({"error": "INVALID_AMOUNT"}))
