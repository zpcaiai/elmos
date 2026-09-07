import unittest
from reference_kernel.elmos_ai_factory.judge_calibration import calibrate,judge_use_decision
class JudgeTests(unittest.TestCase):
 def test_perfect_small_is_bounded(self):
  c=calibrate([True,False]*5,[True,False]*5);self.assertEqual('BOUNDED',judge_use_decision(c,self_judge=False,authoritative=False))
 def test_self_certification_blocked(self):
  c=calibrate([True,False]*20,[True,False]*20);self.assertEqual('BLOCKED',judge_use_decision(c,self_judge=True,authoritative=True))
 def test_bad_judge_blocked(self):
  c=calibrate([True,False]*20,[False,True]*20);self.assertEqual('BLOCKED',judge_use_decision(c,self_judge=False,authoritative=True))
