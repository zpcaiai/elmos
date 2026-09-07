import unittest
from datetime import datetime,timezone
from reference_kernel.elmos_ai_factory.sql_semantics import *
class T(unittest.TestCase):
 def test_empty_null(self):self.assertIsNone(normalize_scalar("",True))
 def test_unordered(self):self.assertTrue(compare_rows([{"id":2},{"id":1}],[{"id":1},{"id":2}])["equivalent"])
 def test_ordered(self):self.assertFalse(compare_rows([{"id":2},{"id":1}],[{"id":1},{"id":2}],ordered=True)["equivalent"])
 def test_transaction_exact(self):self.assertTrue(transaction_equivalent(["a","b"],["a","b"]))
 def test_transaction_noncommute(self):self.assertFalse(transaction_equivalent(["a","b"],["b","a"]))
