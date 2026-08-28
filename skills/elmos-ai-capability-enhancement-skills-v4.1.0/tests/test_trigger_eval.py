import unittest
from reference_kernel.elmos_ai_factory.trigger_eval import TriggerObservation,evaluate_trigger,trigger_gate
class TriggerEvalTests(unittest.TestCase):
 def test_perfect(self):
  m=evaluate_trigger([TriggerObservation(True,True,True),TriggerObservation(False,False,False)])
  self.assertEqual(1,m.precision);self.assertEqual(1,m.recall)
 def test_false_activation(self):
  m=evaluate_trigger([TriggerObservation(False,True,False),TriggerObservation(False,False,False)])
  self.assertEqual('BLOCKED',trigger_gate(m))
 def test_empty_rejected(self):
  with self.assertRaises(ValueError):evaluate_trigger([])
