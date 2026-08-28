import unittest
from datetime import datetime,timedelta,timezone
from reference_kernel.elmos_ai_factory.oversight import Approval,authorize_action
class OversightTests(unittest.TestCase):
 def test_dual_control(self):
  now=datetime.now(timezone.utc);rows=[Approval('d','a','manager','approved',now+timedelta(minutes=5)),Approval('d','b','manager','approved',now+timedelta(minutes=5))]
  self.assertEqual('ALLOW',authorize_action(action_digest='d',approvals=rows,allowed_roles={'manager'},required_distinct=2,now=now))
 def test_digest_mismatch_denied(self):
  now=datetime.now(timezone.utc);rows=[Approval('other','a','manager','approved',now+timedelta(minutes=5))]
  self.assertEqual('DENY',authorize_action(action_digest='d',approvals=rows,allowed_roles={'manager'},required_distinct=1,now=now))
 def test_expired_denied(self):
  now=datetime.now(timezone.utc);rows=[Approval('d','a','manager','approved',now-timedelta(seconds=1))]
  self.assertEqual('DENY',authorize_action(action_digest='d',approvals=rows,allowed_roles={'manager'},required_distinct=1,now=now))
