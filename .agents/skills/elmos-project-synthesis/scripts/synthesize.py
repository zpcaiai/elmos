#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    repository = Path(__file__).resolve().parents[4]
    engine = repository / "engines" / "project-synthesis-engine"
    uv = shutil.which("uv") or "/opt/homebrew/bin/uv"
    command = [uv, "--directory", str(engine), "run", "--locked", "elmos-project-synthesis", *sys.argv[1:]]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
