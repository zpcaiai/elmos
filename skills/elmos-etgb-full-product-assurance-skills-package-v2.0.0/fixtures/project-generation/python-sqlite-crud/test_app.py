import unittest

from app import InventoryService


class InventoryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = InventoryService()

    def test_crud_and_idempotency(self) -> None:
        first = self.service.create_product("SKU-1", 10, "idem-1")
        duplicate = self.service.create_product("DIFFERENT-INPUT-IS-IGNORED", 999, "idem-1")
        self.assertEqual(first, duplicate)
        self.assertEqual(10, self.service.get_product(first.id).stock)
        self.assertEqual([("CREATE", 10)], self.service.audit_events(first.id))

    def test_purchase_is_transactional(self) -> None:
        product = self.service.create_product("SKU-2", 3, "idem-2")
        updated = self.service.purchase(product.id, 2)
        self.assertEqual(1, updated.stock)
        before = self.service.audit_events(product.id)
        with self.assertRaisesRegex(RuntimeError, "INSUFFICIENT_STOCK"):
            self.service.purchase(product.id, 2)
        self.assertEqual(1, self.service.get_product(product.id).stock)
        self.assertEqual(before, self.service.audit_events(product.id))

    def test_parameterization_blocks_injection(self) -> None:
        product = self.service.create_product("x'); DROP TABLE products;--", 1, "idem-3")
        self.assertEqual("x'); DROP TABLE products;--", self.service.get_product(product.id).sku)


if __name__ == "__main__":
    unittest.main()
