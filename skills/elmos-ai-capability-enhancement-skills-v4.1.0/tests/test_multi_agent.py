import unittest
from reference_kernel.elmos_ai_factory.multi_agent import validate_topology,dependency_cycle
class MultiAgentTests(unittest.TestCase):
 def valid(self):return {'agents':[{'id':'a'},{'id':'b'}],'delegations':[{'from':'a','to':'b','parentScope':['read'],'scope':['read']}],'stateOwners':{'x':'a'},'termination':{'maxRounds':3},'budgets':{'tokens':100}}
 def test_valid(self):self.assertFalse(validate_topology(self.valid()))
 def test_scope_expansion(self):
  d=self.valid();d['delegations'][0]['scope']=['write'];self.assertIn('scope-expansion',{i.code for i in validate_topology(d)})
 def test_cycle(self):self.assertTrue(dependency_cycle([('a','b'),('b','a')]))
