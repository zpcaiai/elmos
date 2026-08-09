#!/usr/bin/env python3
"""Stable launcher for the captured, self-contained frontend v2 replay."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    namespace = runpy.run_path(
        str(Path(__file__).with_name("validate_frontend_formal_route_campaign_v2.py")),
        run_name="elmos_frontend_v2_captured_validator",
    )
    raise SystemExit(namespace["main"]())
