"""Unit and integration tests for Enterprise Messaging, DLQ Replay, Redis Lock, and XFetch."""
import time
import pytest

from elmos_project_synthesis.messaging_infrastructure.messaging_middleware_emitter import (
    MessageDeliveryStatus,
    ConsumedMessage,
    IdempotentDeduplicationStore,
    ExponentialBackoffWithJitter,
    DeadLetterQueueManager,
    ResilientMessageConsumerPipeline,
)
from elmos_project_synthesis.messaging_infrastructure.distributed_cache_lock_emitter import (
    MockRedisState,
    RedisClusterLockManager,
    LockHeartbeatDaemon,
    XFetchCacheStampedeGuard,
)


def test_idempotent_deduplication_store():
    store = IdempotentDeduplicationStore(ttl_seconds=1)
    assert not store.is_processed("grp-1", "msg-101")
    store.mark_processed("grp-1", "msg-101")
    assert store.is_processed("grp-1", "msg-101")
    assert not store.is_processed("grp-2", "msg-101") # Different consumer group

    # TTL expiry
    time.sleep(1.05)
    assert not store.is_processed("grp-1", "msg-101")


def test_exponential_backoff_with_jitter():
    policy = ExponentialBackoffWithJitter(base_delay_ms=50.0, max_delay_ms=1000.0, max_attempts=4)

    assert policy.can_retry(1)
    assert policy.can_retry(3)
    assert not policy.can_retry(4)

    # Verify backoff values are bounded by ceiling
    for attempt in range(1, 4):
        delay = policy.compute_backoff_seconds(attempt)
        ceiling = min(1.0, 0.05 * (2 ** (attempt - 1)))
        assert 0.0 <= delay <= ceiling


def test_resilient_consumer_pipeline_and_dlq_routing():
    dedup = IdempotentDeduplicationStore()
    dlq = DeadLetterQueueManager()
    retry_policy = ExponentialBackoffWithJitter(base_delay_ms=5.0, max_delay_ms=20.0, max_attempts=3)

    # 1. Success case
    processed_count = 0
    def success_handler(msg: ConsumedMessage):
        nonlocal processed_count
        processed_count += 1

    pipeline = ResilientMessageConsumerPipeline("grp-orders", success_handler, dedup, retry_policy, dlq)
    msg1 = ConsumedMessage("m1", "orders", 0, 100, "k1", {"order_id": "101"})
    status = pipeline.process_message(msg1)
    assert status == MessageDeliveryStatus.ACKNOWLEDGED
    assert processed_count == 1

    # Idempotent skip
    status_dup = pipeline.process_message(msg1)
    assert status_dup == MessageDeliveryStatus.ACKNOWLEDGED
    assert processed_count == 1 # Not incremented

    # 2. Poison pill case -> routes to DLQ
    attempts_made = 0
    def failing_handler(msg: ConsumedMessage):
        nonlocal attempts_made
        attempts_made += 1
        raise RuntimeError("Permanent DB Error")

    pipeline_fail = ResilientMessageConsumerPipeline("grp-orders", failing_handler, dedup, retry_policy, dlq)
    msg_bad = ConsumedMessage("m-poison", "orders", 0, 101, "k2", {"bad": True})
    status_fail = pipeline_fail.process_message(msg_bad)
    assert status_fail == MessageDeliveryStatus.DEAD_LETTERED
    assert attempts_made == 3 # 3 attempts made before giving up
    assert len(dlq.records) == 1

    # Replay from DLQ
    dlq_id = list(dlq.records.keys())[0]
    replayed_msg = dlq.replay_dead_letter(dlq_id)
    assert replayed_msg is not None
    assert replayed_msg.message_id == "replay-m-poison"
    assert "X-Replayed-From-DLQ" in replayed_msg.headers


def test_redis_cluster_lock_and_fencing_token():
    redis_state = MockRedisState()
    lock_mgr = RedisClusterLockManager(redis_state)

    handle1 = lock_mgr.acquire_lock("lock:order:1001", "worker-A", ttl_seconds=1.0)
    assert handle1 is not None
    assert handle1.is_active
    assert handle1.fencing_token > 1000

    # Second worker cannot acquire while held
    handle2 = lock_mgr.acquire_lock("lock:order:1001", "worker-B", ttl_seconds=1.0, timeout_seconds=0.1)
    assert handle2 is None

    # Safe release
    released = lock_mgr.release_lock(handle1)
    assert released
    assert not handle1.is_active

    # Now worker-B can acquire and gets a higher monotonic fencing token
    handle2_retry = lock_mgr.acquire_lock("lock:order:1001", "worker-B", ttl_seconds=1.0)
    assert handle2_retry is not None
    assert handle2_retry.fencing_token > handle1.fencing_token


def test_lock_heartbeat_daemon_renewal():
    redis_state = MockRedisState()
    lock_mgr = RedisClusterLockManager(redis_state)

    handle = lock_mgr.acquire_lock("lock:task:compute", "daemon-worker", ttl_seconds=0.3)
    assert handle is not None

    daemon = LockHeartbeatDaemon(lock_mgr, handle, heartbeat_interval_seconds=0.1)
    daemon.start()

    # Sleep longer than initial 0.3s TTL; daemon should keep it alive
    time.sleep(0.4)
    assert handle.is_active
    assert not handle.is_expired

    daemon.stop()
    lock_mgr.release_lock(handle)


def test_xfetch_cache_stampede_guard():
    guard = XFetchCacheStampedeGuard(beta=1.5)
    compute_count = 0

    def compute_expensive():
        nonlocal compute_count
        compute_count += 1
        time.sleep(0.01)
        return {"report": 42}

    val1 = guard.get_or_compute("key:report", compute_expensive, ttl_seconds=10.0)
    assert val1 == {"report": 42}
    assert compute_count == 1

    # Immediate second call serves cached value without recomputing
    val2 = guard.get_or_compute("key:report", compute_expensive, ttl_seconds=10.0)
    assert val2 == {"report": 42}
    assert compute_count == 1
