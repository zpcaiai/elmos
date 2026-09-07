"""Unit tests for money arithmetic, ledger entries, and contracts."""

from __future__ import annotations

from decimal import Decimal
import unittest

from elmos_pricing_billing.domain import (
    ContractError,
    Currency,
    Money,
    TenantScope,
)
from elmos_pricing_billing.contracts import (
    canonical_json,
    digest_json,
    require_text,
    validate_money,
)


class DomainTests(unittest.TestCase):
    def test_exact_money_arithmetic(self) -> None:
        m1 = Money(Decimal("10.5000"), Currency.USD)
        m2 = Money(Decimal("4.2500"), Currency.USD)
        self.assertEqual(m1 + m2, Money(Decimal("14.7500"), Currency.USD))
        self.assertEqual(m1 - m2, Money(Decimal("6.2500"), Currency.USD))
        self.assertEqual(m1 * 2, Money(Decimal("21.0000"), Currency.USD))

    def test_currency_mismatch_raises(self) -> None:
        m_usd = Money(Decimal("10.00"), Currency.USD)
        m_eur = Money(Decimal("10.00"), Currency.EUR)
        with self.assertRaises(ContractError):
            _ = m_usd + m_eur

    def test_canonical_json_and_digest(self) -> None:
        obj1 = {"b": 2, "a": 1}
        obj2 = {"a": 1, "b": 2}
        self.assertEqual(canonical_json(obj1), canonical_json(obj2))
        self.assertEqual(digest_json(obj1), digest_json(obj2))


if __name__ == "__main__":
    unittest.main()
