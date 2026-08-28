import unittest
from reference_kernel.elmos_ai_factory.provider_resilience import ProviderCandidate,select_provider
class ProviderTests(unittest.TestCase):
 def test_policy_aware_selection(self):
  rows=[ProviderCandidate('a',True,'jp',frozenset({'tool'}),frozenset({'zdr'}),2),ProviderCandidate('b',True,'us',frozenset({'tool'}),frozenset({'zdr'}),1)]
  self.assertEqual('a',select_provider(rows,required_capabilities=frozenset({'tool'}),allowed_regions=frozenset({'jp'}),required_policy=frozenset({'zdr'})).name)
 def test_no_weak_fallback(self):self.assertIsNone(select_provider([],required_capabilities=frozenset(),allowed_regions=frozenset({'jp'}),required_policy=frozenset()))
