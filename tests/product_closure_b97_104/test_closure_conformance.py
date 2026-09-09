from __future__ import annotations

import unittest

from scripts.product_closure_b97_104.archetypes import (
    BaseClosureArchetype,
    get_closure_archetype,
)
from scripts.product_closure_b97_104.errors import (
    SecurityViolation,
    ValidationError,
)
from scripts.product_closure_b97_104.gate import ProductClosureGate
from scripts.product_closure_b97_104.orchestrator import (
    ClosureBatchReceipt,
    ProductClosureOrchestrator,
)
from scripts.product_closure_b97_104.registry import get_closure_registry


class ProductClosureConformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = get_closure_registry()
        cls.orchestrator = ProductClosureOrchestrator(registry=cls.registry)
        cls.gate = ProductClosureGate()

    def test_all_128_closure_skills_loaded_and_bound(self) -> None:
        self.assertEqual(len(self.registry), 128)
        self.assertEqual(len(self.registry.batches), 8)

        for skill in self.registry.all_skills():
            self.assertTrue(skill.source_id.startswith('B'))
            self.assertTrue(skill.installed_name.startswith('b'))
            self.assertIn(skill.batch, range(97, 105))
            arch = skill.get_archetype_instance()
            self.assertIsInstance(arch, BaseClosureArchetype)

    def test_each_of_8_batches_has_exactly_16_skills(self) -> None:
        for b in range(97, 105):
            skills = self.registry.get_batch(b)
            self.assertEqual(len(skills), 16, f'Batch {b} does not have 16 skills')

    def test_run_each_of_8_closure_batches_end_to_end(self) -> None:
        for b in range(97, 105):
            receipt = self.orchestrator.run_batch(b)
            self.assertEqual(receipt.batch, b)
            self.assertEqual(receipt.skills_executed, 16)
            self.assertEqual(receipt.status, 'LOCAL_EXECUTED')
            self.assertEqual(receipt.certification, 'NOT_CERTIFIED')
            self.assertTrue(receipt.receipt_digest.startswith('sha256:'))
            self.assertTrue(receipt.journal_digest.startswith('sha256:'))

            verdict = self.gate.evaluate(receipt)
            self.assertEqual(verdict.decision, 'LOCAL_PASSED')
            self.assertEqual(verdict.certification, 'NOT_CERTIFIED')
            self.assertEqual(verdict.external_evidence_status, 'NOT_RUN')

    def test_all_128_individual_skills_execute(self) -> None:
        for skill in self.registry.all_skills():
            res_by_id = self.orchestrator.run_skill(skill.source_id, {})
            self.assertEqual(res_by_id['skill_id'], skill.source_id)
            self.assertEqual(res_by_id['status'], 'LOCAL_EXECUTED')
            self.assertEqual(res_by_id['certification'], 'NOT_CERTIFIED')

            res_by_name = self.orchestrator.run_skill(skill.installed_name, {})
            self.assertEqual(res_by_name['installed_name'], skill.installed_name)
            self.assertEqual(res_by_name['output_digest'], res_by_id['output_digest'])

    def test_estate_inventory_closure_archetype(self) -> None:
        arch = get_closure_archetype('estate-inventory-closure')
        out = arch.execute({'skills': ['s1', 's2'], 'aliases': {'s1': 'alias1'}})
        self.assertEqual(out['data']['total_skills'], 2)
        self.assertFalse(out['data']['cycles_detected'])

    def test_contract_certification_closure_archetype(self) -> None:
        arch = get_closure_archetype('contract-certification-closure')
        out = arch.execute({'contract_id': 'TEST_CONTRACT', 'preconditions': ['auth']})
        self.assertEqual(out['data']['contract_id'], 'TEST_CONTRACT')
        self.assertTrue(out['data']['schema_closed'])

    def test_effect_messaging_closure_archetype(self) -> None:
        arch = get_closure_archetype('effect-messaging-closure')
        out = arch.execute({'steps': ['init', 'process', 'finalize']})
        self.assertEqual(len(out['data']['outbox_events']), 3)
        self.assertEqual(out['data']['durable_state'], 'RUNNING')

    def test_sandbox_profile_closure_archetype(self) -> None:
        arch = get_closure_archetype('sandbox-profile-closure')
        out = arch.execute({'runner_id': 'runner-x', 'isolation_level': 'MICROVM'})
        self.assertEqual(out['data']['workload_identity'], 'spiffe://elmos.internal/runner-x')
        self.assertTrue(out['data']['mtls_enforced'])

    def test_route_discovery_closure_archetype(self) -> None:
        arch = get_closure_archetype('route-discovery-closure')
        out = arch.execute({'source_language': 'Java8', 'target_language': 'Java21'})
        self.assertEqual(out['data']['target_language'], 'Java21')
        self.assertTrue(out['data']['strangler_coexistence'])

    def test_verification_testing_closure_archetype(self) -> None:
        arch = get_closure_archetype('verification-testing-closure')
        out = arch.execute({'test_count': 50, 'mutations_killed': 50})
        self.assertEqual(out['data']['mutation_score'], 1.0)
        self.assertEqual(out['data']['tests_executed'], 50)

    def test_independent_verifier_closure_archetype(self) -> None:
        arch = get_closure_archetype('independent-verifier-closure')
        out = arch.execute({'executor_id': 'agent-1', 'verifier_id': 'agent-2'})
        self.assertTrue(out['data']['dual_control_verified'])

        # Separation of duties violation
        with self.assertRaises(ValidationError):
            arch.execute({'executor_id': 'agent-1', 'verifier_id': 'agent-1', 'strict_separation': True})

    def test_release_environment_closure_archetype(self) -> None:
        arch = get_closure_archetype('release-environment-closure')
        out = arch.execute({'environments': ['ci-cleanroom'], 'gate_checks': ['sec', 'dr']})
        self.assertTrue(out['data']['clean_room_benchmarked'])
        self.assertTrue(out['data']['release_ready'])

    def test_security_violation_blocks_execution(self) -> None:
        arch = get_closure_archetype('estate-inventory-closure')
        with self.assertRaises(SecurityViolation):
            arch.execute({'tenant_id': 'unauthorized'})

    def test_gate_rejects_self_signed_certified_claim(self) -> None:
        fake_receipt = ClosureBatchReceipt(
            batch=97,
            package='elmos-codex-skills-batch97-104-complete',
            status='LOCAL_EXECUTED',
            certification='CERTIFIED',
            skills_executed=16,
            receipt_digest='sha256:abc',
            journal_digest='sha256:def',
            timestamp='2026-09-10T00:00:00Z',
            skill_results=[],
        )
        verdict = self.gate.evaluate(fake_receipt)
        self.assertEqual(verdict.decision, 'BLOCKED')
        self.assertTrue(any('Self-claimed CERTIFIED' in b for b in verdict.blockers))

    def test_gate_blocks_on_zero_tolerance_finding(self) -> None:
        receipt = self.orchestrator.run_batch(97)
        verdict = self.gate.evaluate(receipt, findings=['Data leak detected'])
        self.assertEqual(verdict.decision, 'BLOCKED')
        self.assertTrue(any('Zero-tolerance security finding' in b for b in verdict.blockers))


if __name__ == '__main__':
    unittest.main()
