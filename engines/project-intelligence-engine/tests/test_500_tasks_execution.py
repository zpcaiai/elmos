import unittest
from elmos_project_intelligence.task_execution.task_runner import (
    ProjectIntelligenceTaskRunner,
)

class TasksExecutionTests(unittest.TestCase):
    def setUp(self):
        self.runner = ProjectIntelligenceTaskRunner()

    def test_all_500_tasks_loaded(self):
        self.assertEqual(len(self.runner.tasks), 500)
        self.assertEqual(len(self.runner.skill_tasks), 50)

    def test_task_execution_samples(self):
        sample_ids = [
            'ELMOS-PI-00-T01',
            'ELMOS-PI-00-T10',
            'ELMOS-PI-10-T05',
            'ELMOS-PI-25-T03',
            'ELMOS-PI-49-T10',
        ]
        for tid in sample_ids:
            receipt = self.runner.execute_task(tid)
            self.assertEqual(receipt.status, 'COMPLETED')
            self.assertTrue(receipt.acceptance_verified)
            self.assertTrue(receipt.content_digest.startswith('sha256:'))
            self.assertGreater(len(receipt.deliverables), 0)

    def test_execute_batch_00(self):
        receipts = self.runner.execute_batch('BATCH-00-product-and-reference-architecture')
        self.assertGreater(len(receipts), 0)
        for r in receipts:
            self.assertEqual(r.status, 'COMPLETED')

    def test_execute_all_500_tasks(self):
        all_receipts = self.runner.execute_all_tasks()
        self.assertEqual(len(all_receipts), 500)
        for tid, r in all_receipts.items():
            self.assertEqual(r.status, 'COMPLETED')
            self.assertTrue(r.acceptance_verified)
