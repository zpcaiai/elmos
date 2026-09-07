import unittest
from reference_kernel.elmos_ai_factory.supply_chain import PackageTrustInput,trust_decision
class SupplyChainTests(unittest.TestCase):
 def base(self,**kw):
  d=dict(signature_verified=True,publisher_trusted=True,provenance_complete=True,reproducible_build=True,permission_expansions=(),observed_undeclared_behaviors=(),revoked=False);d.update(kw);return PackageTrustInput(**d)
 def test_trusted(self):self.assertEqual('TRUSTED',trust_decision(self.base())[0])
 def test_permission_expansion_blocks(self):self.assertEqual('BLOCKED',trust_decision(self.base(permission_expansions=('network:x',)))[0])
 def test_nonreproducible_bounded(self):self.assertEqual('BOUNDED',trust_decision(self.base(reproducible_build=False))[0])
