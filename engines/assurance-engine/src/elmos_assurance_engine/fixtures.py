"""Implementation of B02: Environment fixtures and synthetic test data factories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import sha256_digest


@dataclass(frozen=True)
class TestFixture:
    fixture_id: str
    target_environment: str
    data: dict[str, Any]

    @property
    def digest(self) -> str:
        return sha256_digest(self.data)


class EnvironmentFixtureFactory:
    """Creates isolated synthetic fixtures without production leakage."""

    @classmethod
    def create_order_fixtures(cls, tenant_id: str) -> TestFixture:
        data = {
            "tenant_id": tenant_id,
            "orders": [
                {
                    "order_id": "ord-001",
                    "customer_id": "cust-001",
                    "amount_cents": 2500,
                    "items": [{"sku": "item-a", "qty": 1, "price_cents": 2500}],
                    "currency": "USD",
                },
                {
                    "order_id": "ord-002",
                    "customer_id": "cust-002",
                    "amount_cents": 4999,
                    "items": [{"sku": "item-b", "qty": 2, "price_cents": 2499}],
                    "currency": "USD",
                },
            ],
            "accounts": [
                {"customer_id": "cust-001", "balance_cents": 10000},
                {"customer_id": "cust-002", "balance_cents": 5000},
            ],
        }
        return TestFixture(
            fixture_id=f"fixture:order:{tenant_id}",
            target_environment="ephemeral-sandbox",
            data=data,
        )
