"""Injectable clock so recovery, TTL and lease tests are deterministic."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float:
        """Seconds since the UNIX epoch, UTC."""


class SystemClock:
    __slots__ = ()

    def now(self) -> float:
        return time.time()


class ManualClock:
    """Test clock. Never used by production code paths."""

    __slots__ = ("_now",)

    def __init__(self, start: float = 1_760_000_000.0) -> None:
        self._now = start

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> float:
        self._now += seconds
        return self._now


SYSTEM_CLOCK: Clock = SystemClock()


def iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
