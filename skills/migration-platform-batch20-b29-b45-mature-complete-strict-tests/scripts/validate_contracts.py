from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in sorted((ROOT / "contracts" / "events").rglob("*.json")):
    with path.open(encoding="utf-8") as handle:
        json.load(handle)
    print(f"validated {path.relative_to(ROOT)}")
