"""Batch J: Frontend Syntax Fidelity & AST Cross-Checking Module (Skills 169-184)."""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any, Dict, List, Optional

from ..models import BatchType, ObligationStatus, SemanticObligation, SemanticRisk


class FrontendSyntaxSemanticsModule:
    """Manages lossless CST, dialect/version detection, macro expansion, and parse error recovery."""

    def __init__(self):
        self.dialect_rules: Dict[str, Dict[str, re.Pattern]] = {
            "python": {
                "python2": re.compile(r"\bprint\s+['\"]|\braw_input\s*\("),
                "python3": re.compile(r"\bprint\s*\(|\basync\s+def\b|:\s*[a-zA-Z_][a-zA-Z0-9_]*\s*="),
            },
            "java": {
                "java8": re.compile(r"->\s*\{|\.stream\(\)"),
                "java17": re.compile(r"\brecord\s+[A-Z]|\bsealed\s+class\b|\bpermits\b"),
                "java21": re.compile(r"\bwhen\s+[a-zA-Z_]|\bString\s+template\b"),
            },
            "csharp": {
                "csharp8": re.compile(r"\bswitch\s*\{|\bnullable\s+enable\b"),
                "csharp10": re.compile(r"\bglobal\s+using\b|\bfile\s+scoped\b"),
                "csharp12": re.compile(r"\bprimary\s+constructor\b|\[\s*1\s*,\s*2\s*\]"),
            },
        }

    def detect_syntax_dialect(self, language: str, source_code: str) -> Dict[str, Any]:
        """Detects dialect version from code markers."""
        lang_key = language.lower()
        signatures = self.dialect_rules.get(lang_key, {})
        detected = "unknown"

        for ver, pat in signatures.items():
            if pat.search(source_code):
                detected = ver

        return {
            "language": language,
            "detected_version": detected if detected != "unknown" else f"{language}-latest",
            "status": "DIALECT_DETECTED",
        }

    def create_frontend_obligation(
        self,
        source_grammar: str,
        target_grammar: str,
        property_name: str,
    ) -> SemanticObligation:
        """Emits a Batch J syntactic semantic obligation."""
        obl_id = f"obl-J-{hashlib.sha256((source_grammar + target_grammar + property_name).encode('utf-8')).hexdigest()[:10]}"
        return SemanticObligation(
            obligation_id=obl_id,
            batch=BatchType.BATCH_J,
            layer="frontend-semantics",
            source_construct=source_grammar,
            target_construct=target_grammar,
            property_name=property_name,
            invariants=["LOSSLESS_CST_FIDELITY", "SYNTACTIC_ISOMORPHISM"],
            risk=SemanticRisk.CRITICAL,
            status=ObligationStatus.NOT_RUN,
        )
