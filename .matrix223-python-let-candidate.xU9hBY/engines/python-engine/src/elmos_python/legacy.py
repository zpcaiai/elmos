from __future__ import annotations

import re
from pathlib import Path


class LegacyPythonAnalyzer:
    """Inventory Python 2 semantic hazards without executing customer code."""

    def assess(self, root: Path) -> dict[str, object]:
        findings: set[str] = set()
        boundaries: list[dict[str, str]] = []
        golden_outputs: set[str] = set()
        compatibility_layers: set[str] = set()
        legacy_candidates: list[str] = []
        for path in sorted(root.rglob("*.py")):
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            source = path.read_text(encoding="utf-8", errors="replace")
            if re.search(r"(?m)^\s*print\s+[^ (]", source) or re.search(r"\bxrange\s*\(", source):
                legacy_candidates.append(relative)
            if re.search(r"\b(str|unicode|bytes|bytearray)\b", source):
                for marker, boundary, output in (
                    (r"(?:open\([^)]*,\s*['\"]?b|\.read\(|\.write\()", "FILE", "FILE_HASH"),
                    (r"(?:request|response|urllib|httplib|socket)", "HTTP", "API_RESPONSE"),
                    (r"(?:json\.|csv\.|database|cursor\.)", "DATA", "DATABASE_CHANGES"),
                    (r"(?:encrypt|decrypt|compress|decompress)", "BINARY_PROTOCOL", "OUTPUT_HASH"),
                ):
                    if re.search(marker, source, re.IGNORECASE):
                        boundaries.append({"path": relative, "boundary": boundary, "classification": "UNKNOWN"})
                        golden_outputs.add(output)
                if boundaries:
                    findings.add("PY2_BYTES_TEXT_AMBIGUOUS")
            if re.search(r"(?m)(?<!/)\b\w+\s*/\s*\w+", source):
                findings.add("PY2_INTEGER_DIVISION_RISK")
            if re.search(r"\b(?:sorted|sort)\([^)]*\)|\.sort\(", source) and re.search(
                r"\b(?:None|str|unicode|int|long)\b", source
            ):
                findings.add("PY2_COMPARISON_SEMANTICS")
            if re.search(r"(?m)^\s*import\s+[A-Za-z_]\w*\s*$", source) and (root / "__init__.py").exists():
                findings.add("PY2_IMPLICIT_RELATIVE_IMPORT")
            if any(name in source for name in ("cPickle", "pickle.loads", "joblib.load")):
                findings.add("PY2_PICKLE_COMPATIBILITY")
            if any(name in source for name in ("six", "future", "__future__")):
                compatibility_layers.update(name for name in ("six", "future", "__future__") if name in source)
        return {
            "transformationCore": "LIBCST_OR_ISOLATED_LEGACY_GRAMMAR_ADAPTER",
            "twoToThreeRole": "CANDIDATE_DIFF_ONLY_NOT_PRODUCTION_CORE",
            "legacyCandidateFiles": legacy_candidates,
            "stringBoundaries": boundaries,
            "findings": sorted(findings),
            "goldenBehavior": sorted(golden_outputs | {"STDOUT", "EXCEPTION_TYPE", "EXIT_CODE"}),
            "compatibilityLayers": [
                {"name": name, "exitPlanRequired": True, "removalDate": "OWNER_APPROVAL_REQUIRED"}
                for name in sorted(compatibility_layers)
            ],
        }
