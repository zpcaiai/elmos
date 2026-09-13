from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Type

logger = logging.getLogger('elmos.foundry.scheduler.retry')

@dataclass
class RetryDecision:
    should_retry: bool
    delay_seconds: float
    attempt: int
    is_fatal: bool
    reason: str

class ErrorClassifier:
    """Classifies errors into fatal vs retryable classes."""

    FATAL_EXCEPTIONS: tuple[Type[Exception], ...] = (
        ValueError,
        TypeError,
        KeyError,
        SyntaxError,
        PermissionError,
        AssertionError,
    )

    RETRYABLE_EXCEPTIONS: tuple[Type[Exception], ...] = (
        TimeoutError,
        ConnectionError,
        IOError,
        OSError,
    )

    @classmethod
    def is_fatal(cls, exc: Exception) -> bool:
        if isinstance(exc, cls.FATAL_EXCEPTIONS):
            return True
        exc_str = str(exc).lower()
        if 'unsupported' in exc_str or 'invalid' in exc_str or 'not found' in exc_str:
            return True
        return False

    @classmethod
    def is_retryable(cls, exc: Exception) -> bool:
        if isinstance(exc, cls.RETRYABLE_EXCEPTIONS):
            return True
        exc_str = str(exc).lower()
        if 'rate limit' in exc_str or 'timeout' in exc_str or 'temporarily unavailable' in exc_str or '503' in exc_str:
            return True
        return not cls.is_fatal(exc)

class RetryPolicy:
    """Resilience retry policy with full jitter exponential backoff, DLQ and compensations."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 10.0,
        jitter_factor: float = 0.5,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter_factor = jitter_factor
        self.dead_letter_queue: List[Dict[str, Any]] = []
        self._compensation_hooks: Dict[str, Callable[[str, Exception], None]] = {}

    def evaluate(self, task_id: str, error: Exception, attempt: int) -> RetryDecision:
        if ErrorClassifier.is_fatal(error):
            return RetryDecision(
                should_retry=False,
                delay_seconds=0.0,
                attempt=attempt,
                is_fatal=True,
                reason=f"Fatal error: {type(error).__name__}: {error}",
            )

        if attempt >= self.max_retries:
            return RetryDecision(
                should_retry=False,
                delay_seconds=0.0,
                attempt=attempt,
                is_fatal=False,
                reason=f"Max retries ({self.max_retries}) exceeded: {error}",
            )

        # Exponential backoff with full jitter
        raw_backoff = min(self.max_delay, self.base_delay * (2 ** attempt))
        jitter = raw_backoff * self.jitter_factor * random.uniform(-1.0, 1.0)
        delay = max(0.05, raw_backoff + jitter)

        return RetryDecision(
            should_retry=True,
            delay_seconds=delay,
            attempt=attempt + 1,
            is_fatal=False,
            reason=f"Retryable error: {type(error).__name__}: {error}",
        )

    def record_dead_letter(self, task_id: str, error: Exception, payload: Dict[str, Any]) -> None:
        entry = {
            'task_id': task_id,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'payload': payload,
            'timestamp': time.time(),
        }
        self.dead_letter_queue.append(entry)
        logger.error("Task %s moved to Dead Letter Queue: %s", task_id, error)

    def register_compensation(self, task_id: str, hook: Callable[[str, Exception], None]) -> None:
        self._compensation_hooks[task_id] = hook

    def trigger_compensation(self, task_id: str, error: Exception) -> bool:
        hook = self._compensation_hooks.get(task_id)
        if hook:
            try:
                hook(task_id, error)
                logger.info("Compensation hook executed successfully for task %s", task_id)
                return True
            except Exception as comp_err:
                logger.error("Compensation hook failed for task %s: %s", task_id, comp_err)
                return False
        return False
