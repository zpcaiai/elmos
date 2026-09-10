import unittest
from elmos_foundry.scheduler import (
    DAGEngine, TaskNode, CycleError,
    WorkerPool,
    CheckpointStore, TaskState, TaskRecord,
    RetryPolicy,
    DistributedTaskScheduler,
)

class SchedulerUnitTests(unittest.TestCase):

    def test_dag_cycle_detection(self) -> None:
        dag = DAGEngine()
        dag.add_node(TaskNode(task_id='A', dependencies=['B']))
        dag.add_node(TaskNode(task_id='B', dependencies=['A']))

        with self.assertRaises(CycleError):
            dag.validate_acyclic()

    def test_dag_waves(self) -> None:
        dag = DAGEngine()
        dag.add_node(TaskNode(task_id='A'))
        dag.add_node(TaskNode(task_id='B'))
        dag.add_node(TaskNode(task_id='C', dependencies=['A', 'B']))
        dag.add_node(TaskNode(task_id='D', dependencies=['C']))

        waves = dag.compute_waves()
        self.assertEqual(len(waves), 3)
        wave0_ids = {t.task_id for t in waves[0].tasks}
        self.assertEqual(wave0_ids, {'A', 'B'})
        self.assertEqual([t.task_id for t in waves[1].tasks], ['C'])
        self.assertEqual([t.task_id for t in waves[2].tasks], ['D'])

    def test_worker_leases_and_fencing(self) -> None:
        pool = WorkerPool(max_workers=2)
        lease = pool.acquire_lease('worker-1', 'task-100', ttl_seconds=10.0)
        self.assertEqual(lease.worker_id, 'worker-1')
        self.assertTrue(pool.verify_lease(lease.lease_id, lease.token))

        # Renew lease
        self.assertTrue(pool.renew_lease(lease.lease_id, 20.0))

        # Release lease
        pool.release_lease(lease.lease_id)
        self.assertFalse(pool.verify_lease(lease.lease_id, lease.token))
        pool.shutdown()

    def test_checkpoint_cas(self) -> None:
        store = CheckpointStore(':memory:')
        rec1 = TaskRecord(task_id='T1', state=TaskState.PENDING, version=1)
        self.assertTrue(store.save_task('graph-1', rec1))

        # Advance state
        rec1.state = TaskState.RUNNING
        self.assertTrue(store.save_task('graph-1', rec1))

        fetched = store.get_task('graph-1', 'T1')
        self.assertIsNotNone(fetched)
        assert fetched is not None
        self.assertEqual(fetched.state, TaskState.RUNNING)

        # Snapshot and restore
        snap = store.snapshot('graph-1')
        store2 = CheckpointStore(':memory:')
        store2.restore('graph-1', snap)
        restored = store2.get_task('graph-1', 'T1')
        assert restored is not None
        self.assertEqual(restored.state, TaskState.RUNNING)

    def test_retry_policy(self) -> None:
        policy = RetryPolicy(max_retries=2, base_delay=0.1)

        # Fatal error
        fatal_dec = policy.evaluate('T1', ValueError('bad value'), 0)
        self.assertFalse(fatal_dec.should_retry)
        self.assertTrue(fatal_dec.is_fatal)

        # Retryable error
        retry_dec = policy.evaluate('T1', TimeoutError('timed out'), 0)
        self.assertTrue(retry_dec.should_retry)

        # Exceeding retries
        retry_dec2 = policy.evaluate('T1', TimeoutError('timed out'), 2)
        self.assertFalse(retry_dec2.should_retry)

    def test_scheduler_execution(self) -> None:
        scheduler = DistributedTaskScheduler(max_workers=4)
        scheduler.submit_task(TaskNode(task_id='step1', payload={'x': 10}))
        scheduler.submit_task(TaskNode(task_id='step2', dependencies=['step1'], payload={'y': 20}))

        def h_step1(task: TaskNode) -> dict:
            return {'val': task.payload['x'] * 2}

        def h_step2(task: TaskNode) -> dict:
            return {'val': task.payload['y'] + 5}

        scheduler.register_handler('step1', h_step1)
        scheduler.register_handler('step2', h_step2)

        result = scheduler.run_graph('test-graph')
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertEqual(result['completed_count'], 2)

        records = result['records']
        self.assertEqual(records['step1'].result, {'val': 20})
        self.assertEqual(records['step2'].result, {'val': 25})
        scheduler.shutdown()

if __name__ == '__main__':
    unittest.main()
