#!/usr/bin/env python3
"""CLI entry for B38-B45 100% industrial physical-middleware certification."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.industrial_certification import main


if __name__ == "__main__":
    raise SystemExit(main())
