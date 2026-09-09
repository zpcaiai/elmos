from __future__ import annotations

import unittest

from scripts.language_packs_b81_95.archetypes import (
    BaseArchetype,
    get_archetype,
)
from scripts.language_packs_b81_95.errors import (
    DifferentialMismatch,
    SecurityViolation,
    ValidationError,
)
from scripts.language_packs_b81_95.gate import LanguagePackGate
from scripts.language_packs_b81_95.orchestrator import LanguagePackOrchestrator
from scripts.language_packs_b81_95.registry import get_registry


class LanguagePackConformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = get_registry()
        cls.orchestrator = LanguagePackOrchestrator(registry=cls.registry)
        cls.gate = LanguagePackGate()

    def test_all_180_skills_loaded_and_bound(self) -> None:
        self.assertEqual(len(self.registry), 180)
        self.assertEqual(len(self.registry.batches), 15)

        for skill in self.registry.all_skills():
            self.assertTrue(skill.source_id.startswith('PG'))
            self.assertTrue(skill.installed_name.startswith('b'))
            self.assertIn(skill.batch, range(81, 96))
            arch = skill.get_archetype_instance()
            self.assertIsInstance(arch, BaseArchetype)

    def test_each_of_15_batches_has_exactly_12_skills(self) -> None:
        for b in range(81, 96):
            skills = self.registry.get_batch(b)
            self.assertEqual(len(skills), 12, f'Batch {b} does not have 12 skills')

    def test_run_each_of_15_batches_end_to_end(self) -> None:
        for b in range(81, 96):
            receipt = self.orchestrator.run_batch(b)
            self.assertEqual(receipt.batch, b)
            self.assertEqual(receipt.skills_executed, 12)
            self.assertEqual(receipt.status, 'LOCAL_EXECUTED')
            self.assertEqual(receipt.certification, 'NOT_CERTIFIED')
            self.assertTrue(receipt.receipt_digest.startswith('sha256:'))
            self.assertTrue(receipt.journal_digest.startswith('sha256:'))

            verdict = self.gate.evaluate(receipt)
            self.assertEqual(verdict.decision, 'LOCAL_PASSED')
            self.assertEqual(verdict.certification, 'NOT_CERTIFIED')
            self.assertEqual(verdict.external_evidence_status, 'NOT_RUN')

    def test_all_180_individual_skills_execute(self) -> None:
        """Execute every single skill individually by name and ID."""
        for skill in self.registry.all_skills():
            res_by_id = self.orchestrator.run_skill(skill.source_id, {})
            self.assertEqual(res_by_id["skill_id"], skill.source_id)
            self.assertEqual(res_by_id["status"], "LOCAL_EXECUTED")
            self.assertEqual(res_by_id["certification"], "NOT_CERTIFIED")

            res_by_name = self.orchestrator.run_skill(skill.installed_name, {})
            self.assertEqual(res_by_name["installed_name"], skill.installed_name)
            self.assertEqual(res_by_name["output_digest"], res_by_id["output_digest"])

    def test_discovery_inventory_archetype(self) -> None:
        arch = get_archetype('discovery-inventory')
        out = arch.execute({
            'sources': [
                {'path': 'src/main.cbl', 'content': 'IDENTIFICATION DIVISION.\nPROGRAM-ID. HELLO.', 'dialect': 'COBOL-85'},
                {'path': 'src/sub.cbl', 'content': 'IDENTIFICATION DIVISION.\nPROGRAM-ID. SUB.', 'dialect': 'COBOL-85'},
            ]
        })
        self.assertEqual(out['status'], 'SUCCESS')
        self.assertEqual(out['data']['total_files'], 2)
        self.assertEqual(out['data']['dialects'], ['COBOL-85'])

    def test_parser_semantic_model_archetype(self) -> None:
        arch = get_archetype('parser-semantic-model')
        out = arch.execute({
            'source_code': 'PROGRAM demo\nVAR total = 0\nIF total > 0 THEN\n  PERFORM calculate\nEND',
            'language': 'COBOL',
        })
        self.assertEqual(out['status'], 'SUCCESS')
        self.assertGreater(out['data']['cst_node_count'], 0)
        self.assertGreater(out['data']['cyclomatic_complexity'], 1)

    def test_schema_data_compiler_archetype(self) -> None:
        arch = get_archetype('schema-data-compiler')
        out = arch.execute({
            'schema_name': 'CUSTOMER_RECORD',
            'fields': [
                {'name': 'CUST_ID', 'type': 'INT', 'length': 4},
                {'name': 'BALANCE', 'type': 'COMP-3', 'length': 8},
            ]
        })
        self.assertEqual(out['data']['field_count'], 2)
        self.assertEqual(out['data']['fields'][1]['target_type'], 'DECIMAL')

    def test_batch_workflow_modeler_archetype(self) -> None:
        arch = get_archetype('batch-workflow-modeler')
        out = arch.execute({
            'workflow_id': 'DAILY_SETTLEMENT',
            'steps': [
                {'id': 'EXTRACT', 'program': 'EXTRACT_PGM', 'depends_on': []},
                {'id': 'TRANSFORM', 'program': 'TRANSFORM_PGM', 'depends_on': ['EXTRACT']},
            ]
        })
        self.assertEqual(out['data']['step_count'], 2)
        self.assertTrue(out['data']['is_acyclic'])

    def test_transaction_modernizer_archetype(self) -> None:
        arch = get_archetype('transaction-modernizer')
        out = arch.execute({
            'transaction_name': 'TRANSFER_FUNDS',
            'resources': ['DEBIT_ACCOUNT', 'CREDIT_ACCOUNT'],
        })
        self.assertEqual(len(out['data']['saga_compensation_steps']), 2)
        self.assertTrue(out['data']['acid_contract']['commit'])

    def test_parallel_run_verifier_detects_mismatch(self) -> None:
        arch = get_archetype('parallel-run-verifier')
        out = arch.execute({
            'test_cases': [
                {'id': 'TC1', 'legacy_output': 100, 'target_output': 100},
                {'id': 'TC2', 'legacy_output': 200, 'target_output': 205},
            ]
        })
        self.assertEqual(out['data']['verdict'], 'DISCREPANCY_DETECTED')
        self.assertEqual(out['data']['passed_cases'], 1)

        with self.assertRaises(DifferentialMismatch):
            arch.execute({
                'strict_fail': True,
                'test_cases': [
                    {'id': 'TC2', 'legacy_output': 200, 'target_output': 205},
                ]
            })

    def test_security_violation_blocks_execution(self) -> None:
        arch = get_archetype('discovery-inventory')
        with self.assertRaises(SecurityViolation):
            arch.execute({'tenant_id': 'unauthorized'})

    def test_gate_rejects_self_signed_certified_claim(self) -> None:
        from scripts.language_packs_b81_95.orchestrator import BatchRunReceipt
        fake_receipt = BatchRunReceipt(
            batch=81,
            package='elmos-language-packs-batch81-95-complete',
            status='LOCAL_EXECUTED',
            certification='CERTIFIED',
            skills_executed=12,
            receipt_digest='sha256:abc',
            journal_digest='sha256:def',
            timestamp='2026-09-10T00:00:00Z',
            skill_results=[],
        )
        verdict = self.gate.evaluate(fake_receipt)
        self.assertEqual(verdict.decision, 'BLOCKED')
        self.assertTrue(any('Self-claimed CERTIFIED' in b for b in verdict.blockers))

    def test_gate_blocks_on_zero_tolerance_finding(self) -> None:
        receipt = self.orchestrator.run_batch(81)
        verdict = self.gate.evaluate(receipt, findings=['Privilege escalation injection detected'])
        self.assertEqual(verdict.decision, 'BLOCKED')
        self.assertTrue(any('Zero-tolerance security finding' in b for b in verdict.blockers))


if __name__ == '__main__':
    unittest.main()
