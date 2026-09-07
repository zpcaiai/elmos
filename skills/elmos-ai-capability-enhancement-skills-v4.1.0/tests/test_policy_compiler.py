import unittest
from reference_kernel.elmos_ai_factory.policy_compiler import PolicyRule,validate_rules,default_decision
class PolicyTests(unittest.TestCase):
 def test_default_deny(self):self.assertEqual('DENY',default_decision([],set()))
 def test_deny_precedence(self):
  rows=[PolicyRule('a','allow',1,'x'),PolicyRule('d','deny',2,'x')];self.assertEqual('DENY',default_decision(rows,{'a','d'}))
 def test_duplicate_invalid(self):self.assertTrue(validate_rules([PolicyRule('x','allow',1,'a'),PolicyRule('x','deny',2,'b')]))
