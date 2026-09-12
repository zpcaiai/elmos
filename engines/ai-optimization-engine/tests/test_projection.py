import unittest
from elmos_ai_optimization.projection import ProjectionCatalog
from elmos_ai_optimization.contracts import ContractError, StaleVersionError

class TestProjection(unittest.TestCase):
    def setUp(self):
        self.catalog = ProjectionCatalog(":memory:")

    def tearDown(self):
        self.catalog.close()

    def test_begin_happy_path(self):
        self.catalog.begin("t1", "r1", "gen-1", "snap-1", 10)
        row = self.catalog.db.execute("SELECT state FROM versions").fetchone()
        self.assertEqual(row[0], "BUILDING")

    def test_begin_invalid_args(self):
        with self.assertRaises(ContractError):
            self.catalog.begin("", "r1", "gen-1", "snap-1", 10)
        with self.assertRaises(ContractError):
            self.catalog.begin("t1", "r1", "gen-1", "snap-1", -1)

    def test_begin_duplicate(self):
        self.catalog.begin("t1", "r1", "gen-1", "snap-1", 10)
        with self.assertRaises(StaleVersionError):
            self.catalog.begin("t1", "r1", "gen-1", "snap-1", 10)

    def test_validate_happy_path(self):
        self.catalog.begin("t1", "r1", "gen-1", "snap-1", 10)
        self.catalog.validate("t1", "r1", "gen-1", 10)
        row = self.catalog.db.execute("SELECT state FROM versions").fetchone()
        self.assertEqual(row[0], "VALIDATED")

    def test_validate_not_found(self):
        with self.assertRaises(StaleVersionError):
            self.catalog.validate("t1", "r1", "gen-1", 10)

    def test_validate_wrong_state(self):
        self.catalog.begin("t1", "r1", "gen-1", "snap-1", 10)
        self.catalog.validate("t1", "r1", "gen-1", 10)
        # Attempt to validate again, now in VALIDATED state
        with self.assertRaises(StaleVersionError):
            self.catalog.validate("t1", "r1", "gen-1", 10)

    def test_validate_count_mismatch(self):
        self.catalog.begin("t1", "r1", "gen-1", "snap-1", 10)
        with self.assertRaises(StaleVersionError):
            self.catalog.validate("t1", "r1", "gen-1", 9)

    def test_get_head_empty(self):
        self.assertIsNone(self.catalog.get_head("t1", "r1"))

    def test_publish_happy_path(self):
        self.catalog.begin("t1", "r1", "gen-1", "snap-1", 10)
        self.catalog.validate("t1", "r1", "gen-1", 10)
        
        self.catalog.publish("t1", "r1", "gen-1", None)
        self.assertEqual(self.catalog.get_head("t1", "r1"), "gen-1")
        
        row = self.catalog.db.execute("SELECT state FROM versions WHERE generation='gen-1'").fetchone()
        self.assertEqual(row[0], "PUBLISHED")

    def test_publish_cas_mismatch(self):
        self.catalog.begin("t1", "r1", "gen-1", "snap-1", 10)
        self.catalog.validate("t1", "r1", "gen-1", 10)
        
        # Expected head is not None but db has None
        with self.assertRaises(StaleVersionError):
            self.catalog.publish("t1", "r1", "gen-1", "gen-0")

    def test_publish_cas_success_subsequent(self):
        self.catalog.begin("t1", "r1", "gen-1", "snap-1", 10)
        self.catalog.validate("t1", "r1", "gen-1", 10)
        self.catalog.publish("t1", "r1", "gen-1", None)
        
        self.catalog.begin("t1", "r1", "gen-2", "snap-2", 20)
        self.catalog.validate("t1", "r1", "gen-2", 20)
        
        # Expected head is gen-1
        self.catalog.publish("t1", "r1", "gen-2", "gen-1")
        self.assertEqual(self.catalog.get_head("t1", "r1"), "gen-2")

    def test_publish_not_found(self):
        with self.assertRaises(StaleVersionError):
            self.catalog.publish("t1", "r1", "gen-1", None)

    def test_publish_wrong_state(self):
        self.catalog.begin("t1", "r1", "gen-1", "snap-1", 10)
        with self.assertRaises(StaleVersionError):
            self.catalog.publish("t1", "r1", "gen-1", None)

if __name__ == '__main__':
    unittest.main()
