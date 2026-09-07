"""Public coverage facade for the v1.1 capability-cell model."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .validation import coverage_report, load_cases


def expected_cases(root: Path) -> Iterable[dict[str, Any]]:
    yield from load_cases(root)
