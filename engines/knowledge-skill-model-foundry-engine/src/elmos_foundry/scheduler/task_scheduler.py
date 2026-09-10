from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set

from .dag_engine import DAGEngine, TaskNode
from .worker_pool import WorkerPool
from .checkpoint import CheckpointStore, TaskRecord, TaskState
from .retry_policy import RetryPolicy

logger = logging.getLogger('elmos.foundry.scheduler')

class DistributedTaskScheduler:
    """Unified Distributed Task Scheduler binding DAG engine, worker pool,
    durable checkpoints, and fault-tolerant retry policy."""

    def __init__(
        self,
        checkpoint_db: str = ':memory:',
        max_workers: int = 8,
        retry_policy: Optional[RetryPolicy] = None,
    ) -> None:
        self.dag_engine = DAGEngine()
        self.worker_pool = WorkerPool(max_workers=max_workers)
        self.checkpoint_store = CheckpointStore(db_path=checkpoint_db)
        self.retry_policy = retry_policy or RetryPolicy()
        self._handlers: Dict[str, Callable[[TaskNode], Dict[str, Any]]] = {}
        self._default_handler: Optional[Callable[[TaskNode], Dict[str, Any]]] = None
        self._is_paused = False
        self._lock = threading.Lock()

    def register_handler(self, key: str, handler: Callable[[TaskNode], Dict[str, Any]]) -> None:
        self._handlers[key] = handler

    def set_default_handler(self, handler: Callable[[TaskNode], Dict[str, Any]]) -> None:
        self._default_handler = handler

    def submit_task(self, node: TaskNode) -> None:
        self.dag_engine.add_node(node)

    def pause(self) -> None:
        self._is_paused = True

    def resume(self) -> None:
        self._is_paused = False

    def run_graph(self, graph_id: str) -> Dict[str, Any]:
        """Executes the registered DAG with full durability, retry loop, and concurrency control."""
        self.dag_engine.validate_acyclic()
        start_time = time.time()

        # Initialize pending records in checkpoint store if not already present
        for t_id in self.dag_engine.nodes.keys():
            existing = self.checkpoint_store.get_task(graph_id, t_id)
            if existing is None:
                self.checkpoint_store.save_task(graph_id, TaskRecord(task_id=t_id, state=TaskState.PENDING))

        all_nodes = self.dag_engine.nodes
        total_tasks = len(all_nodes)
        running_tasks: Dict[str, Any] = {}
        completed_ids: Set[str] = self.checkpoint_store.get_completed_ids(graph_id)
        failed_ids: Set[str] = set()
        attempts: Dict[str, int] = {t_id: 0 for t_id in all_nodes}

        while (len(completed_ids) + len(failed_ids)) < total_tasks:
            if self._is_paused:
                time.sleep(0.1)
                continue

            # Identify ready tasks
            ready_tasks = self.dag_engine.get_ready_tasks(completed_ids, set(running_tasks.keys()))

            # Filter out tasks blocked by failures in dependencies
            executable_tasks: List[TaskNode] = []
            for r_task in ready_tasks:
                if any(dep in failed_ids for dep in r_task.dependencies):
                    # Dependency permanently failed, skip this task
                    rec = TaskRecord(
                        task_id=r_task.task_id,
                        state=TaskState.SKIPPED,
                        error="Skipped due to upstream dependency failure",
                    )
                    self.checkpoint_store.save_task(graph_id, rec)
                    failed_ids.add(r_task.task_id)
                else:
                    executable_tasks.append(r_task)

            # Schedule executable tasks
            for task in executable_tasks:
                worker_id = f'worker-{uuid.uuid4().hex[:6]}'
                lease = self.worker_pool.acquire_lease(worker_id, task.task_id)
                attempts[task.task_id] += 1
                cur_attempt = attempts[task.task_id]

                # Update state to RUNNING
                self.checkpoint_store.save_task(
                    graph_id,
                    TaskRecord(task_id=task.task_id, state=TaskState.RUNNING, attempt=cur_attempt),
                )

                # Select handler
                handler = self._handlers.get(task.task_id)
                if not handler:
                    for tag in task.tags:
                        if tag in self._handlers:
                            handler = self._handlers[tag]
                            break
                if not handler:
                    handler = self._default_handler

                def _execute_task(t: TaskNode = task, h: Optional[Callable[..., Any]] = handler, lease_ref: Any = lease, att: int = cur_attempt) -> Any:
                    try:
                        if not self.worker_pool.verify_lease(lease_ref.lease_id, lease_ref.token):
                            raise PermissionError(f"Worker lease expired or invalid for {t.task_id}")
                        if h is None:
                            # Rehearsal execution
                            return {'status': 'SUCCESS', 'task_id': t.task_id, 'rehearsal': True}
                        return h(t)
                    finally:
                        self.worker_pool.release_lease(lease_ref.lease_id)

                fut = self.worker_pool.submit(_execute_task)
                running_tasks[task.task_id] = fut

            if not running_tasks:
                # No tasks running and no new executable tasks -> graph blocked
                break

            # Poll running futures
            done_ids = []
            for tid, fut in list(running_tasks.items()):
                if fut.done():
                    done_ids.append(tid)
                    try:
                        res = fut.result()
                        # Record success
                        self.checkpoint_store.save_task(
                            graph_id,
                            TaskRecord(
                                task_id=tid,
                                state=TaskState.COMPLETED,
                                attempt=attempts[tid],
                                result=res if isinstance(res, dict) else {'result': str(res)},
                            ),
                        )
                        completed_ids.add(tid)
                    except Exception as exc:
                        # Evaluate retry
                        decision = self.retry_policy.evaluate(tid, exc, attempts[tid])
                        if decision.should_retry:
                            logger.info("Retrying task %s after %.2fs: %s", tid, decision.delay_seconds, decision.reason)
                            time.sleep(decision.delay_seconds)
                            self.checkpoint_store.save_task(
                                graph_id,
                                TaskRecord(
                                    task_id=tid,
                                    state=TaskState.RETRYING,
                                    attempt=attempts[tid],
                                    error=str(exc),
                                ),
                            )
                            # Will be picked up again next loop iteration since not in completed_ids or running_tasks
                        else:
                            # Fatal failure or max retries
                            logger.error("Task %s permanently failed: %s", tid, decision.reason)
                            self.checkpoint_store.save_task(
                                graph_id,
                                TaskRecord(
                                    task_id=tid,
                                    state=TaskState.FAILED,
                                    attempt=attempts[tid],
                                    error=str(exc),
                                ),
                            )
                            self.retry_policy.record_dead_letter(tid, exc, all_nodes[tid].payload)
                            self.retry_policy.trigger_compensation(tid, exc)
                            failed_ids.add(tid)

            for tid in done_ids:
                del running_tasks[tid]

            if running_tasks and not executable_tasks:
                time.sleep(0.02)

        elapsed = time.time() - start_time
        all_records = self.checkpoint_store.get_all_tasks(graph_id)

        return {
            'graph_id': graph_id,
            'total_tasks': total_tasks,
            'completed_count': len(completed_ids),
            'failed_count': len(failed_ids),
            'elapsed_seconds': round(elapsed, 3),
            'status': 'SUCCESS' if len(completed_ids) == total_tasks else 'PARTIAL_FAILURE',
            'records': all_records,
        }

    def shutdown(self) -> None:
        self.worker_pool.shutdown()
