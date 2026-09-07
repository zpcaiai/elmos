import unittest
from reference_kernel.elmos_ai_factory.mcp_tasks import McpTaskBridge,TaskState
class McpTaskTests(unittest.TestCase):
 def task(self):return McpTaskBridge('t','r',1,10)
 def test_stale_fence(self):self.assertEqual('STALE_REJECTED',self.task().update(epoch=1,fencing_token=9,idempotency_key='1',next_state=TaskState.RUNNING))
 def test_duplicate_idempotent(self):
  t=self.task();self.assertEqual('APPLIED',t.update(epoch=1,fencing_token=10,idempotency_key='1',next_state=TaskState.RUNNING));self.assertEqual('DUPLICATE_IGNORED',t.update(epoch=1,fencing_token=10,idempotency_key='1',next_state=TaskState.PAUSED))
 def test_unresolved_side_effect_blocks_completion(self):
  t=self.task();t.update(epoch=1,fencing_token=10,idempotency_key='1',next_state=TaskState.RUNNING);t.unresolved_side_effects=1
  self.assertEqual('SIDE_EFFECTS_UNRESOLVED',t.update(epoch=1,fencing_token=10,idempotency_key='2',next_state=TaskState.COMPLETED))
 def test_rebind_monotonic(self):
  t=self.task();t.rebind(new_epoch=2,new_fencing_token=11);self.assertEqual(2,t.execution_epoch)
