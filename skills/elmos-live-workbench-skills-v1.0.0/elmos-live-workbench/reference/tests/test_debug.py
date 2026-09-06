import unittest
from dataclasses import replace
from lw_core.debug import *

class DebugTests(unittest.TestCase):
    def setUp(self):
        self.l=CommandLedger('t','s')
        self.c=Command('k','t','s',1,1,'next',{},'owner')
    def claim(self,c=None,**kw):return self.l.claim(c or self.c,authorized=True,alive=True,**kw)
    def test_once_pending_not_retry(self):
        self.assertEqual(self.claim(),'EXECUTE_ONCE');self.assertEqual(self.claim(),'RECONCILE_NO_RETRY')
    def test_committed_is_cached(self):
        self.claim();self.l.commit('k',generation=1);self.assertEqual(self.claim(),'CACHED')
    def test_unknown_is_not_replayed(self):
        self.claim();self.l.uncertain('k');self.assertEqual(self.claim(),'RECONCILE_NO_RETRY')
    def test_unknown_cannot_blind_commit(self):
        self.claim();self.l.uncertain('k')
        with self.assertRaises(DebugError):self.l.commit('k',generation=1)
    def test_parameter_conflict(self):
        self.claim()
        with self.assertRaises(DebugError):self.claim(replace(self.c,arguments={'threadId':2}))
    def test_old_epoch_after_continue(self):
        self.l.on_continued()
        with self.assertRaises(DebugError):self.claim()
    def test_new_worker_fences_old(self):
        self.l.replace_worker()
        with self.assertRaises(DebugError):self.claim()
    def test_wrong_tenant(self):
        with self.assertRaises(DebugError):self.claim(replace(self.c,tenant='x'))
    def test_observer_cannot_control(self):
        with self.assertRaises(DebugError):self.claim(replace(self.c,controller='observer'))
    def test_observer_can_inspect_qualified_primitives(self):
        self.assertEqual(self.claim(replace(self.c,name='stackTrace',controller='observer')),'EXECUTE_ONCE')
    def test_eval_denied_by_default(self):
        with self.assertRaises(DebugError):self.claim(replace(self.c,name='evaluate'))
    def test_mutation_is_explicit(self):
        self.assertEqual(self.claim(replace(self.c,name='evaluate'),allow_mutation=True),'EXECUTE_ONCE')
    def test_unsafe_inspection_denied(self):
        with self.assertRaises(DebugError):self.claim(replace(self.c,name='variables'),safe_inspection=False)
    def test_host_exec_denied(self):
        with self.assertRaises(DebugError):self.claim(replace(self.c,name='runInTerminal'))
    def test_permission_revocation(self):
        self.claim();self.l.commit('k',generation=1)
        with self.assertRaises(DebugError):self.l.claim(self.c,authorized=False,alive=True)
    def test_expired_window_denied(self):
        with self.assertRaises(DebugError):self.l.claim(self.c,authorized=True,alive=False)
    def test_unknown_command_denied(self):
        with self.assertRaises(DebugError):self.claim(replace(self.c,name='execSomething'))

    def test_stale_worker_result_cannot_commit(self):
        self.claim();self.l.replace_worker()
        with self.assertRaises(DebugError):self.l.commit('k',generation=1)
