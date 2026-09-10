import pytest
from elmos_foundry.scheduler import (
    DAGEngine, TaskNode, CycleError,
    WorkerPool,
    CheckpointStore, TaskState, TaskRecord,
    RetryPolicy,
    DistributedTaskScheduler,
)

def test_dag_cycle_detection():
    dag = DAGEngine()
    dag.add_node(TaskNode(task_id='A', dependencies=['B']))
    dag.add_node(TaskNode(task_id='B', dependencies=['A']))

    with pytest.raises(CycleError):
        dag.validate_acyclic()

def test_dag_waves():
    dag = DAGEngine()
    dag.add_node(TaskNode(task_id='A'))
    dag.add_node(TaskNode(task_id='B'))
    dag.add_node(TaskNode(task_id='C', dependencies=['A', 'B']))
    dag.add_node(TaskNode(task_id='D', dependencies=['C']))

    waves = dag.compute_waves()
    assert len(waves) == 3
    wave0_ids = {t.task_id for t in waves[0].tasks}
    assert wave0_ids == {'A', 'B'}
    assert [t.task_id for t in waves[1].tasks] == ['C']
    assert [t.task_id for t in waves[2].tasks] == ['D']

def test_worker_leases_and_fencing():
    pool = WorkerPool(max_workers=2)
    lease = pool.acquire_lease('worker-1', 'task-100', ttl_seconds=10.0)
    assert lease.worker_id == 'worker-1'
    assert pool.verify_lease(lease.lease_id, lease.token) is True

    # Renew lease
    assert pool.renew_lease(lease.lease_id, 20.0) is True

    # Release lease
    pool.release_lease(lease.lease_id)
    assert pool.verify_lease(lease.lease_id, lease.token) is False
    pool.shutdown()

def test_checkpoint_cas():
    store = CheckpointStore(':memory:')
    rec1 = TaskRecord(task_id='T1', state=TaskState.PENDING, version=1)
    assert store.save_task('graph-1', rec1) is True

    # Advance state
    rec1.state = TaskState.RUNNING
    assert store.save_task('graph-1', rec1) is True

    fetched = store.get_task('graph-1', 'T1')
    assert fetched is not None
    assert fetched.state == TaskState.RUNNING

    # Snapshot and restore
    snap = store.snapshot('graph-1')
    store2 = CheckpointStore(':memory:')
    store2.restore('graph-1', snap)
    assert store2.get_task('graph-1', 'T1').state == TaskState.RUNNING

def test_retry_policy():
    policy = RetryPolicy(max_retries=2, base_delay=0.1)

    # Fatal error
    fatal_dec = policy.evaluate('T1', ValueError('bad value'), 0)
    assert fatal_dec.should_retry is False
    assert fatal_dec.is_fatal is True

    # Retryable error
    retry_dec = policy.evaluate('T1', TimeoutError('timed out'), 0)
    assert retry_dec.should_retry is True

    # Exceeding retries
    retry_dec2 = policy.evaluate('T1', TimeoutError('timed out'), 2)
    assert retry_dec2.should_retry is False

def test_scheduler_execution():
    scheduler = DistributedTaskScheduler(max_workers=4)
    scheduler.submit_task(TaskNode(task_id='step1', payload={'x': 10}))
    scheduler.submit_task(TaskNode(task_id='step2', dependencies=['step1'], payload={'y': 20}))

    def h_step1(task):
        return {'val': task.payload['x'] * 2}

    def h_step2(task):
        return {'val': task.payload['y'] + 5}

    scheduler.register_handler('step1', h_step1)
    scheduler.register_handler('step2', h_step2)

    result = scheduler.run_graph('test-graph')
    assert result['status'] == 'SUCCESS'
    assert result['completed_count'] == 2

    records = result['records']
    assert records['step1'].result == {'val': 20}
    assert records['step2'].result == {'val': 25}
    scheduler.shutdown()
