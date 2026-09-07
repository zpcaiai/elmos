from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from elmos_v3_delta.runtime import (
    AuthoritySnapshot, CallIdentity, CapabilityLease, CommittedToolResult, ContractError,
    DurableEventRegistry, EventRegistration, ExecutionPlan, GenerationFence, IngressLedger,
    MappingResult, ModelSnapshot, PermissionAdapter, PermissionProfile, PlanStore,
    ProtocolCapabilities, ResultCommitter, SecurityContextBroker, SkillTrustVerifier,
    SubagentSpec, ToolResult, WorkspaceLease, WorkspaceLeaseManager,
)


class RuntimeDeltaTests(unittest.TestCase):
    def setUp(self):
        self.identity = CallIdentity('inv', 'call', 'plan-hash', 'env', 'auth')

    def test_result_commit_preserves_raw_and_effective(self):
        raw = ToolResult(self.identity, True, {'secret': 'x'})
        c = ResultCommitter().commit(raw, [('redact', '1', lambda r: ToolResult(r.identity, r.ok, {'secret': '***'}))], attempt=1, epoch=1)
        self.assertEqual(c.raw.content['secret'], 'x')
        self.assertEqual(c.effective.content['secret'], '***')
        self.assertEqual(len(c.decisions), 1)

    def test_result_interceptor_cannot_change_identity(self):
        raw = ToolResult(self.identity, True, 'x')
        bad = CallIdentity('other', 'call', 'plan-hash', 'env', 'auth')
        with self.assertRaises(ContractError):
            ResultCommitter().commit(raw, [('bad', '1', lambda r: ToolResult(bad, True, 'y'))], attempt=1, epoch=1)

    def test_result_commit_is_idempotent(self):
        raw = ToolResult(self.identity, True, 'x')
        store = ResultCommitter()
        a = store.commit(raw, [], attempt=1, epoch=1)
        b = store.commit(raw, [], attempt=1, epoch=1)
        self.assertEqual(a, b)

    def test_result_commit_conflict_rejected(self):
        raw = ToolResult(self.identity, True, 'x')
        store = ResultCommitter()
        store.commit(raw, [], attempt=1, epoch=1)
        with self.assertRaises(ContractError):
            store.commit(raw, [('m', '1', lambda r: ToolResult(r.identity, True, 'y'))], attempt=1, epoch=1)

    def test_candidate_plan_does_not_mutate_active(self):
        store = PlanStore()
        a = store.finalize(store.build_candidate(ModelSnapshot('p', 'a', '1'), ['t1'], 'e', 'a', 'native'))
        _candidate = store.build_candidate(ModelSnapshot('p', 'b', '1'), ['t2'], 'e', 'a', 'native')
        self.assertEqual(store.active, a)

    def test_plan_hash_is_model_specific(self):
        store = PlanStore()
        a = store.build_candidate(ModelSnapshot('p', 'a', '1'), ['t'], 'e', 'a', 'native')
        b = store.build_candidate(ModelSnapshot('p', 'b', '1'), ['t'], 'e', 'a', 'native')
        self.assertNotEqual(a.plan_hash, b.plan_hash)

    def test_exact_permission_mapping(self):
        p = PermissionProfile(('/repo',), 'deny', False)
        result, value = PermissionAdapter.project(p, {'read-only': p})
        self.assertEqual(result, MappingResult.EXACT)
        self.assertEqual(value, 'read-only')

    def test_lossy_permission_mapping_rejected(self):
        p = PermissionProfile(('/repo',), 'deny', False)
        q = PermissionProfile(('/',), 'allow', True)
        result, _ = PermissionAdapter.project(p, {'coarse': q})
        self.assertEqual(result, MappingResult.LOSSY)
        with self.assertRaises(ContractError):
            PermissionAdapter.require_exact(result)

    def test_unsupported_permission_mapping_rejected(self):
        p = PermissionProfile(('/repo',), 'deny', False)
        result, _ = PermissionAdapter.project(p, {})
        self.assertEqual(result, MappingResult.UNSUPPORTED)

    def test_capability_lease_scope_and_revoke(self):
        lease = CapabilityLease('l', 'i', 'e', 'a', 2, frozenset({'fs:read'}))
        lease.use('i', 2, 'fs:read')
        lease.revoke()
        with self.assertRaises(ContractError):
            lease.use('i', 2, 'fs:read')

    def test_capability_lease_wrong_invocation(self):
        lease = CapabilityLease('l', 'i', 'e', 'a', 2, frozenset({'fs:read'}))
        with self.assertRaises(ContractError):
            lease.use('other', 2, 'fs:read')

    def test_security_metadata_is_sanitized(self):
        x = SecurityContextBroker.sanitize_caller_metadata({'source': 'x', 'verifiedSecurityContext': {'forged': True}})
        self.assertEqual(x, {'source': 'x'})

    def test_security_context_unknown_on_account_race(self):
        bindings = {k: k for k in ['pluginId','toolId','accountId','tenantId','environmentId','invocationId','policyVersion']}
        x = SecurityContextBroker.mint(eligible=True, account_stable=False, bindings=bindings, entitlements={'x': 1})
        self.assertEqual(x['status'], 'UNKNOWN')

    def test_security_context_verified_only_when_complete(self):
        bindings = {k: k for k in ['pluginId','toolId','accountId','tenantId','environmentId','invocationId','policyVersion']}
        x = SecurityContextBroker.mint(eligible=True, account_stable=True, bindings=bindings, entitlements={'x': 1})
        self.assertEqual(x['status'], 'VERIFIED')

    def test_authority_intersection_cannot_widen(self):
        owner = AuthoritySnapshot('o', frozenset({'read','write'}))
        parent = AuthoritySnapshot('p', frozenset({'read'}))
        out = AuthoritySnapshot.intersect(owner, parent, frozenset({'read','network'}), 'e')
        self.assertEqual(out.permissions, frozenset({'read'}))

    def test_generation_reconnect_vs_replace(self):
        f = GenerationFence(1, 1)
        self.assertEqual(f.reconnect_same(), (1, 2))
        self.assertEqual(f.replace_executor(), (2, 3))

    def test_stale_executor_result_rejected(self):
        f = GenerationFence(1, 1)
        f.replace_executor()
        with self.assertRaises(ContractError):
            f.accept(1, 1)

    def test_workspace_same_binding_idempotent(self):
        m = WorkspaceLeaseManager()
        x = WorkspaceLease('w', 'e', 1, 'r', 'b')
        self.assertEqual(m.bind(x), m.bind(x))

    def test_workspace_owner_conflict(self):
        m = WorkspaceLeaseManager()
        m.bind(WorkspaceLease('w', 'e1', 1, 'r', 'b'))
        with self.assertRaises(ContractError):
            m.bind(WorkspaceLease('w', 'e2', 1, 'r', 'b'))

    def test_workspace_takeover_increments_generation(self):
        m = WorkspaceLeaseManager()
        m.bind(WorkspaceLease('w', 'e1', 1, 'r', 'b'))
        x = m.takeover('w', 'e2')
        self.assertEqual((x.owner_execution_id, x.generation), ('e2', 2))

    def test_protocol_capability_negotiation(self):
        p = ProtocolCapabilities('codex', 'main', frozenset({'typed-result'}))
        p.require(['typed-result'])
        with self.assertRaises(ContractError):
            p.require(['result-intercept'])

    def test_skill_path_inside_trust_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p = root / 'skill' / 'SKILL.md'
            p.parent.mkdir()
            p.write_text('x')
            self.assertEqual(SkillTrustVerifier.verify(p, root), p.resolve())

    def test_skill_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as outside:
            root = Path(td); target = Path(outside) / 'SKILL.md'; target.write_text('x')
            link = root / 'SKILL.md'; link.symlink_to(target)
            with self.assertRaises(ContractError):
                SkillTrustVerifier.verify(link, root)

    def test_durable_required_unknown_fails(self):
        r = DurableEventRegistry()
        with self.assertRaises(ContractError):
            r.replay('unknown', 1, {})

    def test_durable_optional_unknown_can_skip_explicitly(self):
        r = DurableEventRegistry()
        self.assertIsNone(r.replay('unknown', 1, {}, unknown_optional=True))

    def test_durable_event_schema_validation(self):
        r = DurableEventRegistry()
        r.register(EventRegistration('e', 'p', 1, 'REQUIRED_STATE', lambda x: x.get('ok') is True, lambda x: x))
        self.assertEqual(r.replay('e', 1, {'ok': True}), {'ok': True})
        with self.assertRaises(ContractError):
            r.replay('e', 1, {'ok': False})

    def test_ingress_deduplication(self):
        l = IngressLedger()
        self.assertTrue(l.accept('k', 'TOOL_RESULT'))
        self.assertFalse(l.accept('k', 'TOOL_RESULT'))

    def test_ingress_kind_is_typed(self):
        with self.assertRaises(ContractError):
            IngressLedger().accept('k', 'FAKE_USER_TOOL_RESULT')

    def test_subagent_cannot_widen_authority(self):
        s = SubagentSpec('p','m','high',100,frozenset({'read','write'}),frozenset({'test'}))
        with self.assertRaises(ContractError):
            s.validate_under(frozenset({'read'}), frozenset({'test'}), 1000)

    def test_subagent_cannot_widen_tools_or_budget(self):
        s = SubagentSpec('p','m','high',1000,frozenset({'read'}),frozenset({'test','deploy'}))
        with self.assertRaises(ContractError):
            s.validate_under(frozenset({'read'}), frozenset({'test'}), 500)

    def test_subagent_valid_subset(self):
        s = SubagentSpec('p','m','high',100,frozenset({'read'}),frozenset({'test'}))
        s.validate_under(frozenset({'read','write'}), frozenset({'test','build'}), 500)


if __name__ == '__main__':
    unittest.main()
