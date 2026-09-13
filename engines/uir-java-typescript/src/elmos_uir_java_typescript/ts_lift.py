from __future__ import annotations
import re
from typing import Any

class TsLifter:
    def lift(self, source: str) -> dict:
        # Simplified parser for TS to UIR-like structure
        return {"type": "Module", "types": []}
