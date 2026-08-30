"""Digest-bound Lean 4 and Dafny verification-source generation.

This module only produces candidate source and a replayable verification
request. It does not execute either native verifier and therefore cannot issue
a proof certificate. Native execution is delegated to the permit-bound,
digest-pinned adapters in :mod:`elmos_formal_assurance.execution`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .canonical import digest_bytes, digest_value, validate_digest, validate_identifier


class FormalProofBridgeError(ValueError):
    """Raised when a proof-source request is incomplete or unsafe."""


_LEAN_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_']{0,127}$")
_DAFNY_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_GENERATOR_VERSION = "elmos-formal-proof-source/v1"
_LEAN_TRUST_ESCAPE = re.compile(
    r"(?mi)(?:\bsorry\b|\badmit\b|\baxiom\b|\bunsafe\b)"
)
_DAFNY_TRUST_ESCAPE = re.compile(
    r"(?mi)(?:\{:verify\s+false\}|\{:axiom\b|\bassume\b|\bexpect\b)"
)


class Lean4Generator:
    """Generate candidate Lean 4 source without asserting native success."""

    @staticmethod
    def generate_theorem(
        theorem_name: str,
        hypotheses: Sequence[str],
        conclusion: str,
        tactics: Sequence[str] | None = None,
    ) -> str:
        name = _language_identifier(theorem_name, "Lean", _LEAN_IDENTIFIER)
        checked_hypotheses = _text_sequence(hypotheses, "hypotheses")
        checked_conclusion = _formal_text(conclusion, "conclusion")
        checked_tactics = (
            _text_sequence(tactics, "tactics") if tactics is not None else ()
        )
        hypothesis_text = "".join(
            f" (h{index} : {value})"
            for index, value in enumerate(checked_hypotheses)
        )
        if checked_tactics:
            proof_body = "\n  ".join(checked_tactics)
        else:
            # Deliberately invalid Lean: a missing proof must never compile as a
            # successful certificate through `sorry`, `admit` or an axiom.
            proof_body = "ELMOS_PROOF_BODY_REQUIRED"
        source = (
            "-- Generated verification candidate; native Lean execution NOT_RUN.\n"
            f"theorem {name}{hypothesis_text} : {checked_conclusion} := by\n"
            f"  {proof_body}\n"
        )
        _reject_trust_escape(source, "Lean")
        return source

    @staticmethod
    def generate_arithmetic_invariance_proof(
        theorem_name: str,
        var_name: str = "x",
        var_type: str = "Int",
        lower_bound: int = 0,
        upper_bound: int = 1000,
    ) -> str:
        name = _language_identifier(theorem_name, "Lean", _LEAN_IDENTIFIER)
        variable = _language_identifier(var_name, "Lean", _LEAN_IDENTIFIER)
        checked_type = _formal_text(var_type, "var_type", maximum=128)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in (lower_bound, upper_bound)):
            raise FormalProofBridgeError("bounds must be integers")
        if lower_bound > upper_bound:
            raise FormalProofBridgeError("lower_bound must not exceed upper_bound")
        return (
            "-- Generated verification candidate; native Lean execution NOT_RUN.\n"
            f"theorem {name} ({variable} : {checked_type}) "
            f"(_h_lower : {variable} >= {lower_bound}) "
            f"(_h_upper : {variable} <= {upper_bound}) :\n"
            f"  {variable} + 0 = {variable} := by\n"
            "  simp\n"
        )


class DafnyGenerator:
    """Generate candidate Dafny source without asserting native success."""

    @staticmethod
    def generate_method(
        method_name: str,
        params: Sequence[Mapping[str, str]],
        returns: Sequence[Mapping[str, str]],
        requires: Sequence[str],
        ensures: Sequence[str],
        body: str | None = None,
    ) -> str:
        name = _language_identifier(method_name, "Dafny", _DAFNY_IDENTIFIER)
        checked_params = _dafny_bindings(params, "params")
        checked_returns = _dafny_bindings(returns, "returns")
        checked_requires = _text_sequence(requires, "requires")
        checked_ensures = _text_sequence(ensures, "ensures")
        if not checked_ensures:
            raise FormalProofBridgeError("Dafny method requires at least one postcondition")
        checked_body = _formal_text(body, "body") if body is not None else None
        param_text = ", ".join(f"{item['name']}: {item['type']}" for item in checked_params)
        return_text = ", ".join(f"{item['name']}: {item['type']}" for item in checked_returns)
        contract_lines = [*(f"requires {item}" for item in checked_requires), *(f"ensures {item}" for item in checked_ensures)]
        contracts = "\n  ".join(contract_lines)
        body_text = checked_body or "ELMOS_BODY_REQUIRED;"
        source = (
            "// Generated verification candidate; native Dafny execution NOT_RUN.\n"
            f"method {name}({param_text}) returns ({return_text})\n"
            f"  {contracts}\n"
            "{\n"
            f"  {body_text}\n"
            "}\n"
        )
        _reject_trust_escape(source, "Dafny")
        return source

    @staticmethod
    def generate_loop_invariance(
        method_name: str,
        param_name: str = "n",
        invariant_cond: str = "0 <= i <= n",
    ) -> str:
        name = _language_identifier(method_name, "Dafny", _DAFNY_IDENTIFIER)
        parameter = _language_identifier(param_name, "Dafny", _DAFNY_IDENTIFIER)
        invariant = _formal_text(invariant_cond, "invariant_cond")
        return (
            "// Generated verification candidate; native Dafny execution NOT_RUN.\n"
            f"method {name}({parameter}: int) returns (sum: int)\n"
            f"  requires {parameter} >= 0\n"
            "  ensures sum >= 0\n"
            "{\n"
            "  var i := 0;\n"
            "  sum := 0;\n"
            f"  while i < {parameter}\n"
            f"    invariant {invariant}\n"
            "    invariant sum >= 0\n"
            f"    decreases {parameter} - i\n"
            "  {\n"
            "    sum := sum + i;\n"
            "    i := i + 1;\n"
            "  }\n"
            "}\n"
        )


class FormalProofKernelBridge:
    """Build a deterministic request for separately authorized native verification."""

    def __init__(self) -> None:
        self.lean_gen = Lean4Generator()
        self.dafny_gen = DafnyGenerator()

    def synthesize_proof_certificate(
        self,
        obligation_name: str,
        formula: str,
        source_lang: str = "generic",
        target_lang: str = "generic",
        context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a verification request; never fabricate a proof certificate."""

        obligation = validate_identifier(obligation_name, "obligationName")
        checked_formula = _formal_text(formula, "formula", maximum=256 * 1024)
        source = validate_identifier(source_lang, "sourceLang")
        target = validate_identifier(target_lang, "targetLang")
        supplied_context = dict(context or {})
        unknown = set(supplied_context) - {"lean4", "dafny", "assumptionHash", "tcbHash", "environmentDigest"}
        if unknown:
            raise FormalProofBridgeError(
                "unsupported proof bridge context fields: " + ", ".join(sorted(unknown))
            )
        bindings: dict[str, str] = {}
        for field in ("assumptionHash", "tcbHash", "environmentDigest"):
            if field in supplied_context:
                bindings[field] = validate_digest(supplied_context[field], field)

        generated: dict[str, dict[str, Any]] = {}
        gaps: list[str] = []
        formula_digest = digest_bytes(checked_formula.encode("utf-8"))
        lean_context = supplied_context.get("lean4")
        if lean_context is not None:
            lean = _mapping(lean_context, "lean4")
            unknown_lean = set(lean) - {
                "hypotheses",
                "conclusion",
                "tactics",
                "semanticMappingDigest",
            }
            if unknown_lean:
                raise FormalProofBridgeError(
                    "unsupported lean4 fields: " + ", ".join(sorted(unknown_lean))
                )
            tactics = lean.get("tactics")
            source_text = self.lean_gen.generate_theorem(
                obligation,
                _sequence(lean.get("hypotheses", ()), "lean4.hypotheses"),
                _required_text(lean, "conclusion", "lean4.conclusion"),
                _sequence(tactics, "lean4.tactics") if tactics is not None else None,
            )
            mapping_digest = _optional_digest(
                lean.get("semanticMappingDigest"), "lean4.semanticMappingDigest"
            )
            generated["lean4"] = _generated_source(
                source_text,
                complete=tactics is not None and bool(tactics),
                semantic_mapping_digest=mapping_digest,
            )
            if mapping_digest is None:
                gaps.append("LEAN4_SEMANTIC_MAPPING_EVIDENCE_REQUIRED")
            if not tactics:
                gaps.append("LEAN4_PROOF_BODY_REQUIRED")
        else:
            gaps.append("LEAN4_SOURCE_NOT_GENERATED")

        dafny_context = supplied_context.get("dafny")
        if dafny_context is not None:
            dafny = _mapping(dafny_context, "dafny")
            unknown_dafny = set(dafny) - {
                "params",
                "returns",
                "requires",
                "ensures",
                "body",
                "semanticMappingDigest",
            }
            if unknown_dafny:
                raise FormalProofBridgeError(
                    "unsupported dafny fields: " + ", ".join(sorted(unknown_dafny))
                )
            body = dafny.get("body")
            source_text = self.dafny_gen.generate_method(
                obligation,
                _sequence(dafny.get("params", ()), "dafny.params"),
                _sequence(dafny.get("returns", ()), "dafny.returns"),
                _sequence(dafny.get("requires", ()), "dafny.requires"),
                _sequence(dafny.get("ensures", ()), "dafny.ensures"),
                body if isinstance(body, str) else None,
            )
            if body is not None and not isinstance(body, str):
                raise FormalProofBridgeError("dafny.body must be a string")
            mapping_digest = _optional_digest(
                dafny.get("semanticMappingDigest"), "dafny.semanticMappingDigest"
            )
            generated["dafny"] = _generated_source(
                source_text,
                complete=body is not None,
                semantic_mapping_digest=mapping_digest,
            )
            if mapping_digest is None:
                gaps.append("DAFNY_SEMANTIC_MAPPING_EVIDENCE_REQUIRED")
            if body is None:
                gaps.append("DAFNY_BODY_REQUIRED")
        else:
            gaps.append("DAFNY_SOURCE_NOT_GENERATED")

        request_document = {
            "format": "elmos-native-proof-verification-request/v1",
            "generatorVersion": _GENERATOR_VERSION,
            "obligationName": obligation,
            "formulaDigest": formula_digest,
            "sourceLanguage": source,
            "targetLanguage": target,
            "bindings": bindings,
            "generatedSources": generated,
            "gaps": sorted(gaps),
        }
        request_digest = digest_value(request_document)
        return {
            "artifact_kind": "PROOF_VERIFICATION_REQUEST",
            "request_id": "proof-request-" + request_digest.removeprefix("sha256:")[:24],
            "request_digest": request_digest,
            "obligation_name": obligation,
            "formula_digest": formula_digest,
            "source_lang": source,
            "target_lang": target,
            "generated_sources": generated,
            "generator_version": _GENERATOR_VERSION,
            "verification_status": "NATIVE_VERIFICATION_NOT_RUN",
            "proof_status": "NOT_RUN",
            "soundness_guarantee": "NOT_ASSESSED",
            "certificate_issued": False,
            "external_evidence_status": "NOT_RUN",
            "independent_verification_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
            "gaps": sorted(gaps),
        }


_formal_bridge = FormalProofKernelBridge()


def get_formal_proof_bridge() -> FormalProofKernelBridge:
    """Retrieve the stateless proof-source bridge."""
    return _formal_bridge


def generate_lean4_proof(
    obligation_name: str,
    formula: str,
    source_lang: str = "generic",
    target_lang: str = "generic",
    *,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compatibility helper returning a non-certified verification request."""
    return _formal_bridge.synthesize_proof_certificate(
        obligation_name=obligation_name,
        formula=formula,
        source_lang=source_lang,
        target_lang=target_lang,
        context=context,
    )


def _formal_text(value: Any, path: str, *, maximum: int = 64 * 1024) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise FormalProofBridgeError(f"{path} must be non-empty text without NUL")
    encoded = value.encode("utf-8")
    if len(encoded) > maximum:
        raise FormalProofBridgeError(f"{path} exceeds the size bound")
    return value


def _reject_trust_escape(source: str, language: str) -> None:
    pattern = _LEAN_TRUST_ESCAPE if language == "Lean" else _DAFNY_TRUST_ESCAPE
    if pattern.search(source):
        raise FormalProofBridgeError(
            f"{language} proof source contains a forbidden trust escape"
        )


def _language_identifier(value: Any, language: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise FormalProofBridgeError(f"{language} identifier is invalid")
    return value


def _sequence(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)):
        raise FormalProofBridgeError(f"{path} must be an array")
    if len(value) > 256:
        raise FormalProofBridgeError(f"{path} exceeds the item bound")
    return value


def _text_sequence(value: Sequence[Any], path: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise FormalProofBridgeError(f"{path} must be an array")
    if len(value) > 256:
        raise FormalProofBridgeError(f"{path} exceeds the item bound")
    return tuple(_formal_text(item, f"{path}[{index}]") for index, item in enumerate(value))


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise FormalProofBridgeError(f"{path} must be an object")
    return dict(value)


def _required_text(value: Mapping[str, Any], field: str, path: str) -> str:
    if field not in value:
        raise FormalProofBridgeError(f"{path} is required")
    return _formal_text(value[field], path)


def _optional_digest(value: Any, path: str) -> str | None:
    return None if value is None else validate_digest(value, path)


def _dafny_bindings(
    values: Sequence[Mapping[str, str]], path: str
) -> tuple[dict[str, str], ...]:
    result: list[dict[str, str]] = []
    names: set[str] = set()
    for index, value in enumerate(values):
        mapping = _mapping(value, f"{path}[{index}]")
        if set(mapping) != {"name", "type"}:
            raise FormalProofBridgeError(
                f"{path}[{index}] must contain exactly name and type"
            )
        name = _language_identifier(
            mapping["name"], "Dafny", _DAFNY_IDENTIFIER
        )
        if name in names:
            raise FormalProofBridgeError(f"{path} contains duplicate name {name}")
        names.add(name)
        result.append(
            {"name": name, "type": _formal_text(mapping["type"], "type", maximum=256)}
        )
    return tuple(result)


def _generated_source(
    source: str, *, complete: bool, semantic_mapping_digest: str | None
) -> dict[str, Any]:
    return {
        "source": source,
        "sourceDigest": digest_bytes(source.encode("utf-8")),
        "sourceCompleteness": "CANDIDATE_COMPLETE" if complete else "INCOMPLETE",
        "semanticMappingDigest": semantic_mapping_digest,
        "nativeExecutionStatus": "NOT_RUN",
    }


__all__ = [
    "DafnyGenerator",
    "FormalProofBridgeError",
    "FormalProofKernelBridge",
    "Lean4Generator",
    "generate_lean4_proof",
    "get_formal_proof_bridge",
]
