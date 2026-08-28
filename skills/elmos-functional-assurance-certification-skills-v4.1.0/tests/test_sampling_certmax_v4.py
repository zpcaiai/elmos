import unittest
from reference_kernel.elmos_ai_factory.sampling import *
class T(unittest.TestCase):
 def test_sample(self): self.assertGreater(finite_population_sample_size(1000),100)
 def test_allocate(self): self.assertEqual(set(proportional_allocation({"a":3,"b":1},40)),{"a","b"})
