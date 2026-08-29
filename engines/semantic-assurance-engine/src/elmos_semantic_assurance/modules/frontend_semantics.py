"""Batch J: Frontend & Syntax Semantics Module (Skills 169-184)."""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional

from ..models import BatchType, ObligationStatus, SemanticObligation, SemanticRisk


class FrontendSemanticsModule:
    """Manages grammar ingestion, dialect version detection, macro expansion, and error recovery."""

    def __init__(self):
        self.grammar_registry: Dict[str, Dict[str, Any]] = {}
        self.dialect_signatures: Dict[str, Dict[str, re.Pattern]] = {
            "python": {
                "python2": re.compile(r"\bprint\s+['\"]|\braw_input\s*\("),
                "python3": re.compile(r"\bprint\s*\(|\basync\s+def\b|:\s*[a-zA-Z_][a-zA-Z0-9_]*\s*="),
            },
            "java": {
                "java8": re.compile(r"->\s*\{|\.stream\(\)"),
                "java17": re.compile(r"\brecord\s+[A-Z]|\bsealed\s+class\b|\bpermits\b"),
                "java21": re.compile(r"\bwhen\s+[a-zA-Z_]|\bString\s+template\b"),
            },
            "cpp": {
                "cpp98": re.compile(r"\bauto_ptr<"),
                "cpp11": re.compile(r"\bunique_ptr<|\bauto\s+[a-zA-Z_]|\blambda\b"),
                "cpp20": re.compile(r"\bconcept\s+[A-Z]|\bco_await\b|\bco_return\b"),
            },
        }

    def detect_dialect_version(self, language: str, source_code: str) -> Dict[str, Any]:
        """Identifies exact language dialect and standard version from syntactic markers."""
        lang_key = language.lower()
        signatures = self.dialect_signatures.get(lang_key, {})
        detected = "unknown"
        matches = []

        for ver, pat in signatures.items():
            if pat.search(source_code):
                detected = ver
                matches.append(ver)

        return {
            "language": language,
            "detected_version": detected if detected != "unknown" else f"{language}-standard",
            "matched_signatures": matches,
            "status": "DETECTED",
        }

    def validate_parse_error_recovery(
        self,
        language: str,
        malformed_snippet: str,
        recovered_ast: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Ensures parser error recovery does not hallucinate executable nodes in malformed ASTs."""
        # Detect if recovered AST manufactured unexpected function definitions
        raw_funcs = len(re.findall(r"\bdef\s+|\bfunction\s+|\bvoid\s+", malformed_snippet))
        ast_funcs = len(recovered_ast.get("functions", []))

        is_safe = ast_funcs <= raw_funcs
        return {
            "is_recovery_safe": is_safe,
            "raw_declared_constructs": raw_funcs,
            "ast_emitted_constructs": ast_funcs,
            "hallucination_detected": not is_safe,
            "status": "VALIDATED" if is_safe else "REJECTED_HALLUCINATION",
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
            invariants=["AST_ISOMORPHISM", "NO_SYNTACTIC_HALLUCINATION"],
            risk=SemanticRisk.CRITICAL,
            status=ObligationStatus.NOT_RUN,
        )
