import unittest
from reference_kernel.elmos_ai_factory.skill_ir import validate_skill_ir, permission_expansions, portability_decision

class SkillIRTests(unittest.TestCase):
 def valid(self):
  return {'skillId':'x','version':'1','trigger':{'description':'Use for x'},'instructions':[{'id':'i'}],'resources':[{'path':'scripts/run.py','kind':'script','executable':True,'digest':'sha256:'+'a'*64}],'authority':{'defaultDecision':'deny'},'tests':[{'expectedActivation':False}]}
 def test_valid_skill(self): self.assertTrue(validate_skill_ir(self.valid()).valid)
 def test_path_traversal_blocked(self):
  d=self.valid();d['resources'][0]['path']='../x';self.assertFalse(validate_skill_ir(d).valid)
 def test_permission_expansion(self): self.assertEqual({'network':('b',)},permission_expansions({'network':['a']},{'network':['a','b']}))
 def test_critical_loss_blocks(self): self.assertEqual('BLOCKED',portability_decision([{'status':'unsupported','critical':True}],{}))
