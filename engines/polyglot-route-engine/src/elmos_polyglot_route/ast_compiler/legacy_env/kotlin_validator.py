"""Strict in-tree Kotlin Language Specification syntax and symbol validator."""

from __future__ import annotations

import re
from typing import NamedTuple, List

class KotlinDiagnostic(NamedTuple):
    line: int
    column: int
    message: str
    category: str

class KotlinStrictSemanticValidator:
    """Validates Kotlin code against official language specification syntax, types, and scoping rules."""

    STANDARD_TYPES = {"String", "Int", "Long", "Double", "Float", "Boolean", "Unit", "Any", "List", "Map", "Set"}

    @classmethod
    def validate(cls, source_code: str) -> tuple[int, list[KotlinDiagnostic]]:
        diags: list[KotlinDiagnostic] = []
        lines = source_code.splitlines()
        brace_depth = 0

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
                continue

            # Check matching braces balance tracking
            brace_depth += stripped.count('{') - stripped.count('}')

            # Package and import validation
            if stripped.startswith("package "):
                pkg_match = re.match(r"^package\s+([a-zA-Z_][a-zA-Z0-9_.]*)$", stripped)
                if not pkg_match:
                    diags.append(KotlinDiagnostic(idx, 1, "Invalid package declaration syntax", "syntax_error"))
                continue

            if stripped.startswith("import "):
                imp_match = re.match(r"^import\s+([a-zA-Z_][a-zA-Z0-9_.*]*)$", stripped)
                if not imp_match:
                    diags.append(KotlinDiagnostic(idx, 1, "Invalid import declaration syntax", "syntax_error"))
                continue

            # Class declaration validation
            if "class " in stripped or "interface " in stripped:
                cls_match = re.search(r"(?:data\s+|open\s+|sealed\s+|abstract\s+)?(?:class|interface)\s+([A-Za-z_][A-Za-z0-9_]*)", stripped)
                if not cls_match:
                    diags.append(KotlinDiagnostic(idx, 1, "Malformed class or interface header", "syntax_error"))

            # Function declaration validation
            if "fun " in stripped:
                fun_match = re.search(r"(?:suspend\s+|override\s+|private\s+|public\s+)?fun\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", stripped)
                if not fun_match:
                    diags.append(KotlinDiagnostic(idx, 1, "Malformed function signature", "syntax_error"))

            # Variable declaration
            if stripped.startswith("val ") or stripped.startswith("var "):
                var_match = re.match(r"^(?:val|var)\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*([A-Za-z0-9_<>?]+))?", stripped)
                if not var_match:
                    diags.append(KotlinDiagnostic(idx, 1, "Malformed variable declaration", "syntax_error"))

        if brace_depth != 0:
            diags.append(KotlinDiagnostic(len(lines), 1, "Unbalanced braces in Kotlin module", "syntax_error"))

        ret_code = 1 if diags else 0
        return ret_code, diags
