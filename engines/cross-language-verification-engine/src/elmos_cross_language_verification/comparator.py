from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

@dataclass
class DiffReport:
    path: str
    source_value: Any
    target_value: Any
    diff_type: str


class OutputComparator:
    @classmethod
    def compare_json(cls, source: Any, target: Any, tolerance: float = 1e-9) -> tuple[bool, list[DiffReport]]:
        if isinstance(source, dict) and isinstance(target, dict):
            diffs = []
            all_keys = set(source.keys()) | set(target.keys())
            match = True
            for k in all_keys:
                if k not in source:
                    diffs.append(DiffReport(k, None, target[k], "EXTRA"))
                    match = False
                elif k not in target:
                    diffs.append(DiffReport(k, source[k], None, "MISSING"))
                    match = False
                else:
                    m, sub_diffs = cls.compare_json(source[k], target[k], tolerance)
                    if not m:
                        match = False
                        for sd in sub_diffs:
                            sd.path = f"{k}.{sd.path}"
                            diffs.append(sd)
            return match, diffs
        
        if isinstance(source, list) and isinstance(target, list):
            if len(source) != len(target):
                return False, [DiffReport("", source, target, "LENGTH_MISMATCH")]
            match = True
            diffs = []
            for i, (s_val, t_val) in enumerate(zip(source, target)):
                m, sub_diffs = cls.compare_json(s_val, t_val, tolerance)
                if not m:
                    match = False
                    for sd in sub_diffs:
                        sd.path = f"[{i}].{sd.path}"
                        diffs.append(sd)
            return match, diffs

        if isinstance(source, (int, float)) and isinstance(target, (int, float)):
            if math.isclose(source, target, abs_tol=tolerance):
                return True, []
            return False, [DiffReport("", source, target, "VALUE_MISMATCH")]

        if source == target:
            return True, []
        
        if type(source) != type(target):
            # Try some normalization (e.g., None vs null handling, though in Python JSON parses to None)
            if source is None and target is None:
                return True, []
            return False, [DiffReport("", source, target, "TYPE_MISMATCH")]

        return False, [DiffReport("", source, target, "VALUE_MISMATCH")]

    @classmethod
    def compare_text(cls, source: str, target: str, normalize_whitespace: bool = True) -> bool:
        if normalize_whitespace:
            return " ".join(source.split()) == " ".join(target.split())
        return source == target

    @classmethod
    def compare_structured(cls, source: Any, target: Any, schema: dict[str, Any]) -> bool:
        match, _ = cls.compare_json(source, target)
        return match
