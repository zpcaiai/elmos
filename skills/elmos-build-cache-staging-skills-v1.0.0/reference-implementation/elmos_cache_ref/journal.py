from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


class AppendOnlyJournal:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, event: dict[str, Any]) -> int:
        events = self.read_all()
        sequence = len(events) + 1
        payload = dict(event)
        payload["sequence"] = sequence
        line = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8") + b"\n"

        with self._lock:
            fd = os.open(
                self.path,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o600,
            )
            try:
                os.write(fd, line)
                os.fsync(fd)
            finally:
                os.close(fd)
        return sequence

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        result: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"invalid journal line {line_number}: {exc}"
                    ) from exc
                expected = len(result) + 1
                if event.get("sequence") != expected:
                    raise ValueError(
                        f"journal sequence gap at line {line_number}: "
                        f"expected {expected}, got {event.get('sequence')}"
                    )
                result.append(event)
        return result
