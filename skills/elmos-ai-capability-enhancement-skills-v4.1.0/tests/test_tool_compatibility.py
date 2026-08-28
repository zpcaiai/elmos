import unittest
from reference_kernel.elmos_ai_factory.tool_compatibility import ToolContract,compare_tools
class ToolCompatibilityTests(unittest.TestCase):
 def c(self,**kw):
  d=dict(required_inputs=frozenset({'a'}),optional_inputs=frozenset(),output_fields=frozenset({'x'}),effect='read',idempotent=True,approval='none',retry_class='safe');d.update(kw);return ToolContract(**d)
 def test_same(self):self.assertEqual('COMPATIBLE',compare_tools(self.c(),self.c())[0])
 def test_effect_blocks(self):self.assertEqual('BLOCKED',compare_tools(self.c(),self.c(effect='write'))[0])
 def test_removed_output_bounded(self):self.assertEqual('BOUNDED',compare_tools(self.c(),self.c(output_fields=frozenset()))[0])
