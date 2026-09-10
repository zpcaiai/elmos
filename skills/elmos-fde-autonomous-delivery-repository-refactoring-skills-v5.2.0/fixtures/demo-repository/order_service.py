from dataclasses import dataclass

@dataclass
class Order:
    order_id: str
    idempotency_key: str
    amount: int

class OrderService:
    # Intentional fixture defect: retries can append duplicate orders.
    def __init__(self) -> None:
        self.orders: list[Order] = []

    def create(self, order_id: str, idempotency_key: str, amount: int) -> Order:
        order = Order(order_id, idempotency_key, amount)
        self.orders.append(order)
        return order
