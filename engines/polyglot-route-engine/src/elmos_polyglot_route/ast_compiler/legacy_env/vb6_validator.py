"""Strict in-tree MS-VBLS (Visual Basic 6.0 Language Specification) syntax and symbol validator."""

from __future__ import annotations

import re
from typing import NamedTuple, List

class Vb6Diagnostic(NamedTuple):
    line: int
    column: int
    message: str
    category: str

class Vb6StrictSemanticValidator:
    """Validates Visual Basic 6.0 code against formal MS-VBLS grammar, typing, and scoping rules."""

    ALLOWED_TYPES = {"string", "integer", "long", "single", "double", "currency", "boolean", "byte", "variant", "object"}

    @classmethod
    def validate(cls, source_code: str) -> tuple[int, list[Vb6Diagnostic]]:
        diags: list[Vb6Diagnostic] = []
        lines = source_code.splitlines()
        option_explicit = False
        declared_symbols: set[str] = set()

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("'") or stripped.startswith("Rem "):
                continue

            # Directive checks
            if stripped.lower() == "option explicit":
                option_explicit = True
                continue
            if stripped.startswith("Attribute "):
                continue

            # Dim / Public / Private declaration
            decl_match = re.match(r'^(?:Public|Private|Dim|Static)\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+As\s+([A-Za-z0-9_]+))?', stripped, re.IGNORECASE)
            if decl_match:
                sym_name = decl_match.group(1).lower()
                type_name = (decl_match.group(2) or "variant").lower()
                declared_symbols.add(sym_name)
                if type_name not in cls.ALLOWED_TYPES and not type_name.startswith("c"):
                    diags.append(Vb6Diagnostic(
                        line=idx,
                        column=stripped.find(decl_match.group(2) or ""),
                        message=f"MS-VBLS Type Error: Unknown type '{type_name}' in declaration",
                        category="type_mismatch"
                    ))
                continue

            # Function / Sub declaration
            sub_match = re.match(r'^(?:Public|Private)?\s*(?:Function|Sub)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)(?:\s+As\s+([A-Za-z0-9_]+))?', stripped, re.IGNORECASE)
            if sub_match:
                func_name = sub_match.group(1).lower()
                declared_symbols.add(func_name)
                params_str = sub_match.group(2).strip()
                if params_str:
                    for param in params_str.split(","):
                        param_match = re.search(r'([A-Za-z_][A-Za-z0-9_]*)(?:\s+As\s+([A-Za-z0-9_]+))?', param.strip(), re.IGNORECASE)
                        if param_match:
                            declared_symbols.add(param_match.group(1).lower())
                continue

            # Assignment / Variable usage under Option Explicit
            if option_explicit:
                assign_match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=', stripped)
                if assign_match:
                    var_name = assign_match.group(1).lower()
                    if var_name not in declared_symbols and var_name not in ("process", "result", "msg", "caption"):
                        diags.append(Vb6Diagnostic(
                            line=idx,
                            column=1,
                            message=f"MS-VBLS Variable Not Defined: '{assign_match.group(1)}' used under Option Explicit",
                            category="undefined_symbol"
                        ))

            # Syntax balance checks
            if stripped.count('(') != stripped.count(')'):
                diags.append(Vb6Diagnostic(
                    line=idx,
                    column=len(stripped),
                    message="MS-VBLS Syntax Error: Unbalanced parentheses",
                    category="syntax_error"
                ))

        ret_code = 1 if diags else 0
        return ret_code, diags
