from decimal import Decimal
import json

TWOPLACES = Decimal("0.01")


def money(value: str) -> Decimal:
    return Decimal(value).quantize(TWOPLACES)


class Ledger:
    def __init__(self) -> None:
        self.balances = {"A": money("100.00"), "B": money("25.50")}
        self.history: list[str] = []

    def transfer(self, source: str, target: str, value: str) -> None:
        amount = money(value)
        if amount <= 0:
            raise ValueError("INVALID_AMOUNT")
        if self.balances[source] < amount:
            raise RuntimeError("INSUFFICIENT_FUNDS")
        self.balances[source] -= amount
        self.balances[target] += amount
        self.history.append(f"{source}->{target}:{amount:.2f}")

    def deposit(self, account: str, value: str) -> None:
        amount = money(value)
        self.balances[account] += amount
        self.history.append(f"deposit:{account}:{amount:.2f}")


ledger = Ledger()
ledger.transfer("A", "B", "12.35")
ledger.deposit("B", "0.10")
error = ""
try:
    ledger.transfer("A", "B", "1000.00")
except RuntimeError as exc:
    error = str(exc)

print(json.dumps({
    "balances": {key: f"{value:.2f}" for key, value in ledger.balances.items()},
    "error": error,
    "history": ledger.history,
    "total": f"{sum(ledger.balances.values(), Decimal('0.00')):.2f}",
}, separators=(",", ":"), sort_keys=True))
