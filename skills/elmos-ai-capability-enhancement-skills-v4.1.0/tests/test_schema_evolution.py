import unittest
from reference_kernel.elmos_ai_factory.schema_evolution import backward_compatibility,evolution_decision
class SchemaEvolutionTests(unittest.TestCase):
 def test_add_optional_compatible(self):self.assertFalse(backward_compatibility({'type':'object','properties':{'a':{'type':'string'}}},{'type':'object','properties':{'a':{'type':'string'},'b':{'type':'string'}}}))
 def test_new_required_blocks(self):
  issues=backward_compatibility({'type':'object','properties':{}},{'type':'object','properties':{'b':{'type':'string'}},'required':['b']});self.assertEqual('BLOCKED',evolution_decision(issues,migration_present=False,consumer_tests_pass=True))
 def test_type_change_bounded_with_migration(self):
  issues=backward_compatibility({'type':'object','properties':{'a':{'type':'string'}}},{'type':'object','properties':{'a':{'type':'integer'}}});self.assertEqual('BOUNDED',evolution_decision(issues,migration_present=True,consumer_tests_pass=True))
