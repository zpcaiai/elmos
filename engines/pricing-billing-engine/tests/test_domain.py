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
        self.assertEqual(m1 / 2, Money(Decimal("5.2500"), Currency.USD))
        self.assertEqual(-m1, Money(Decimal("-10.5000"), Currency.USD))
        self.assertEqual(abs(-m1), m1)

    def test_division_by_zero_raises(self) -> None:
        m = Money(Decimal("10.0000"), Currency.USD)
        with self.assertRaises(ZeroDivisionError):
            _ = m / 0

    def test_money_comparisons(self) -> None:
        m_low = Money(Decimal("10.0000"), Currency.USD)
        m_high = Money(Decimal("20.0000"), Currency.USD)
        m_equal = Money(Decimal("10.0000"), Currency.USD)

        self.assertTrue(m_low < m_high)
        self.assertTrue(m_low <= m_high)
        self.assertTrue(m_low <= m_equal)
        self.assertTrue(m_high > m_low)
        self.assertTrue(m_high >= m_low)
        self.assertTrue(m_low >= m_equal)
        self.assertEqual(m_low, m_equal)
        self.assertNotEqual(m_low, m_high)

    def test_money_cross_currency_comparison_raises(self) -> None:
        m_usd = Money(Decimal("10.00"), Currency.USD)
        m_cny = Money(Decimal("10.00"), Currency.CNY)
        with self.assertRaises(ContractError):
            _ = m_usd < m_cny
        with self.assertRaises(ContractError):
            _ = m_usd > m_cny

    def test_money_quantization_bankers_rounding(self) -> None:
        # Quantizes to 0.0001
        m = Money(Decimal("10.12345"), Currency.USD)
        self.assertEqual(m.amount, Decimal("10.1234"))
        m_round_up = Money(Decimal("10.12355"), Currency.USD)
        self.assertEqual(m_round_up.amount, Decimal("10.1236"))

    def test_currency_mismatch_raises(self) -> None:
        m_usd = Money(Decimal("10.00"), Currency.USD)
        m_eur = Money(Decimal("10.00"), Currency.EUR)
        with self.assertRaises(ContractError):
            _ = m_usd + m_eur
        with self.assertRaises(ContractError):
            _ = m_usd - m_eur

    def test_canonical_json_and_digest(self) -> None:
        obj1 = {"b": 2, "a": 1}
        obj2 = {"a": 1, "b": 2}
        self.assertEqual(canonical_json(obj1), canonical_json(obj2))
        self.assertEqual(digest_json(obj1), digest_json(obj2))

    def test_tenant_scope_validation(self) -> None:
        valid_scope = TenantScope(tenant_id="t1", organization_id="org1", project_id="p1")
        self.assertEqual(valid_scope.tenant_id, "t1")
        self.assertEqual(valid_scope.actor_id, "system")

        with self.assertRaises(ContractError):
            TenantScope(tenant_id="", organization_id="org1", project_id="p1")

        with self.assertRaises(ContractError):
            TenantScope(tenant_id="t1", organization_id="", project_id="p1")

    def test_require_text_and_validate_money_contracts(self) -> None:
        self.assertEqual(require_text("hello", "field"), "hello")
        with self.assertRaises(ValueError):
            require_text("", "field")
        with self.assertRaises(ValueError):
            require_text(None, "field")  # type: ignore

        m = validate_money("25.50", Currency.USD)
        self.assertEqual(m.amount, Decimal("25.5000"))
        self.assertEqual(m.currency, Currency.USD)


if __name__ == "__main__":
    unittest.main()

