import unittest
from order_service import OrderService

class OrderServiceTest(unittest.TestCase):
    def test_create(self):
        service = OrderService()
        self.assertEqual("o-1", service.create("o-1", "k-1", 10).order_id)

if __name__ == "__main__":
    unittest.main()
