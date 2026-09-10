"""Fail-closed reference evaluator with actual Ed25519 evidence verification.

Operator-approved requests, identity mappings, expected evidence inventory and
clock are TRUSTED inputs. Reports and repositories cannot configure that trust.
The output is always a DEMO decision, never a production certificate.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "contracts" / "schemas"
MAX_REPORT_BYTES = 2_000_000
MAX_JSON_INTEGER = 2**53 - 1
GATE_KINDS = {
    "E0": {"build"},
    "E1": {"build", "contract"},
    "E2": {"build", "contract", "smoke"},
    "E3": {"build", "contract", "smoke", "regression"},
    "E4": {"build", "contract", "smoke", "regression", "differential", "mutation"},
    "E5": {"build", "contract", "smoke", "regression", "differential", "mutation", "proof", "audit"},
}


def canonical(value: Any) -> bytes:
    """Canonical bytes for THIS demo protocol only, not RFC 8785 or DSSE.

    Reject floats, non-string dictionary keys, and non-interoperable integers.
    Decimal amounts must be serialized as strings in signed metadata.
    """
    def check(v: Any, depth: int = 0) -> None:
        if depth > 64:
            raise ValueError("JSON_DEPTH_LIMIT")
        if v is None or type(v) in (str, bool):
            return
        if type(v) is int and abs(v) <= MAX_JSON_INTEGER:
            return
        if type(v) is list:
            for item in v:
                check(item, depth + 1)
            return
        if type(v) is dict and all(type(k) is str for k in v):
            for item in v.values():
                check(item, depth + 1)
            return
        raise ValueError("UNSUPPORTED_CANONICAL_VALUE")
    check(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def strict_loads(raw: bytes | str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    def no_float(_: str) -> Any:
        raise ValueError("FLOAT_NOT_ALLOWED_IN_SIGNED_METADATA")
    value = json.loads(raw, object_pairs_hook=pairs, parse_float=no_float,
                       parse_constant=no_float)
    canonical(value)
    return value


@lru_cache(maxsize=32)
def validator(name: str) -> Draft202012Validator:
    # Only module-controlled names are used, never a file path from a repo.
    path = SCHEMA_DIR / (name + ".schema.json")
    schema = strict_loads(path.read_bytes())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def require_schema(name: str, value: Any) -> None:
    errors = sorted(validator(name).iter_errors(value), key=lambda e: str(e.path))
    if errors:
        raise ValueError("SCHEMA_INVALID:" + name + ":" + str(list(errors[0].path)))


def signing_message(key_id: str, payload: dict[str, Any]) -> bytes:
    return b"elmos-demo-envelope-v1\x00" + key_id.encode("ascii") + b"\x00" + canonical(payload)


def evidence_basis(envelopes: list[dict[str, Any]]) -> str:
    """Audit commitment to exact, signed, non-audit evidence envelopes."""
    selected = [e for e in envelopes if e.get("payload", {}).get("kind") != "audit"]
    return digest(sorted(selected, key=lambda e: e.get("payload", {}).get("evidence_id", "")))


@dataclass(frozen=True)
class TrustedKey:
    public_key: Ed25519PublicKey
    control_domain: str
    allowed_kinds: frozenset[str]
    tenant_ids: frozenset[str]
    valid_from: int = 0
    valid_until: int = MAX_JSON_INTEGER
    revoked: bool = False


@dataclass(frozen=True)
class TrustedContext:
    """Construct in an operator-controlled boundary, NOT from submission JSON.

    expected_evidence_ids must come from the sealed runner/event inventory.
    This prevents the submitter from omitting a known failed attempt.
    """
    keys: Mapping[str, TrustedKey]
    approved_request_digest: str
    expected_evidence_ids: frozenset[str]
    actual_builder_control_domain: str
    approved_auditor_domains: frozenset[str]
    revoked_request_digests: frozenset[str] = frozenset()
    min_mutation_score_basis_points: int = 8000  # DEMO policy, not a commercial target.
    minimum_audit_challenges: int = 1


def _decision(verdict: str, request_digest: str | None,
              reasons: list[str], verified: list[str]) -> dict[str, Any]:
    result = {
        "schema_version": "4.0", "kind": "DEMO_ONLY_NOT_A_CERTIFICATE",
        "verdict": verdict, "request_digest": request_digest,
        "reasons": sorted(set(reasons)),
        "verified_evidence_ids": sorted(set(verified)),
        "production_signing_allowed": False,
    }
    require_schema("gate-decision", result)
    return result


def evaluate(request: dict[str, Any], envelopes: list[dict[str, Any]],
             blobs: Mapping[str, bytes], context: TrustedContext,
             now: int) -> dict[str, Any]:
    """Validate evidence and calculate a bounded reference verdict.

    No file execution, network requests, KMS access, or production signing.
    All failures of untrusted structure/authentication become INCONCLUSIVE.
    A verified counterexample or violated required gate results in FAIL.
    """
    uncertain: list[str] = []
    failed: list[str] = []
    verified: list[str] = []
    request_hash: str | None = None
    try:
        require_schema("run-request", request)
        request_hash = digest(request)
        if request_hash != context.approved_request_digest:
            return _decision("INCONCLUSIVE", request_hash, ["REQUEST_NOT_APPROVED"], [])
        if request_hash in context.revoked_request_digests:
            return _decision("INCONCLUSIVE", request_hash, ["REQUEST_REVOKED"], [])
        if request["builder_control_domain"] != context.actual_builder_control_domain:
            return _decision("INCONCLUSIVE", request_hash, ["BUILDER_IDENTITY_MISMATCH"], [])
        if type(now) is not int or now < 0:
            raise ValueError("INVALID_TRUSTED_CLOCK")
        if not 0 <= context.min_mutation_score_basis_points <= 10000:
            raise ValueError("INVALID_TRUSTED_MUTATION_THRESHOLD")
        if context.minimum_audit_challenges < 1:
            raise ValueError("INVALID_TRUSTED_AUDIT_POLICY")
        identity_domains: dict[bytes, str] = {}
        for trusted_key in context.keys.values():
            raw_key = trusted_key.public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            prior = identity_domains.get(raw_key)
            if prior is not None and prior != trusted_key.control_domain:
                raise ValueError("CRYPTO_KEY_SHARED_ACROSS_CONTROL_DOMAINS")
            identity_domains[raw_key] = trusted_key.control_domain
        obligations = {o["id"]: o for o in request["obligations"]}
        if len(obligations) != len(request["obligations"]):
            raise ValueError("DUPLICATE_OBLIGATION_ID")
        required_kinds = GATE_KINDS[request["target_level"]]
        supplied_kinds = {o["kind"] for o in obligations.values()}
        if not required_kinds <= supplied_kinds:
            uncertain.append("REQUIRED_GATE_OMITTED_FROM_PLAN")
        if type(envelopes) is not list or not context.expected_evidence_ids:
            raise ValueError("EMPTY_OR_INVALID_EVIDENCE_INVENTORY")
        # Validate structure before calculating a commitment or reading values.
        for envelope in envelopes:
            require_schema("signed-envelope", envelope)
        ids = [e["payload"]["evidence_id"] for e in envelopes]
        if len(ids) != len(set(ids)):
            uncertain.append("DUPLICATE_EVIDENCE_ID")
        if set(ids) != context.expected_evidence_ids:
            uncertain.append("SEALED_EVIDENCE_INVENTORY_MISMATCH")
        basis = evidence_basis(envelopes)
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError) as exc:
        return _decision("INCONCLUSIVE", request_hash, ["INPUT_REJECTED:" + str(exc)], [])

    satisfied: set[tuple[str, str]] = set()
    expected = {(o["id"], c) for o in obligations.values() for c in o["case_ids"]}
    for envelope in envelopes:
        p = envelope["payload"]
        eid = p["evidence_id"]
        try:
            key = context.keys.get(envelope["key_id"])
            if key is None:
                raise ValueError("UNTRUSTED_SIGNER")
            if key.revoked or not key.valid_from <= now < key.valid_until:
                raise ValueError("SIGNER_REVOKED_OR_EXPIRED")
            if p["kind"] not in key.allowed_kinds:
                raise ValueError("SIGNER_KIND_NOT_AUTHORIZED")
            if request["tenant_id"] not in key.tenant_ids:
                raise ValueError("SIGNER_TENANT_NOT_AUTHORIZED")
            signature = base64.b64decode(envelope["signature"], validate=True)
            key.public_key.verify(signature, signing_message(envelope["key_id"], p))
            for attr in ("tenant_id", "project_id", "run_id"):
                if p[attr] != request[attr]:
                    raise ValueError("SUBJECT_IDENTITY_MISMATCH:" + attr)
            if p["request_digest"] != request_hash:
                raise ValueError("REVISION_OR_REQUEST_MISMATCH")
            if not p["issued_at"] <= now < p["expires_at"]:
                raise ValueError("EVIDENCE_STALE_OR_FUTURE")
            if p["expires_at"] <= p["issued_at"]:
                raise ValueError("EVIDENCE_TIME_ORDER")
            for oid in p["obligation_ids"]:
                if oid not in obligations or obligations[oid]["kind"] != p["kind"]:
                    raise ValueError("OBLIGATION_KIND_MISMATCH")
            raw = blobs.get(p["report_digest"])
            if not isinstance(raw, bytes) or len(raw) > MAX_REPORT_BYTES:
                raise ValueError("REPORT_MISSING_OR_OVERSIZED")
            if bytes_digest(raw) != p["report_digest"]:
                raise ValueError("REPORT_DIGEST_MISMATCH")
            report = strict_loads(raw)
            require_schema("verification-report", report)
            if report["kind"] != p["kind"]:
                raise ValueError("REPORT_KIND_MISMATCH")
            pairs = [(r["obligation_id"], r["case_id"]) for r in report["results"]]
            expected_here = {(oid, c) for oid in p["obligation_ids"] for c in obligations[oid]["case_ids"]}
            if len(pairs) != len(set(pairs)) or set(pairs) != expected_here:
                raise ValueError("EXECUTED_CASE_MANIFEST_MISMATCH")
            if p["kind"] == "audit":
                if key.control_domain == context.actual_builder_control_domain:
                    raise ValueError("AUDITOR_NOT_INDEPENDENT_CONTROL_DOMAIN")
                if key.control_domain not in context.approved_auditor_domains:
                    raise ValueError("AUDITOR_DOMAIN_NOT_APPROVED")
                a = report["audit_checks"]
                if a["basis_digest"] != basis:
                    raise ValueError("AUDIT_BASIS_MISMATCH")
                if not a["independence_reviewed"]:
                    raise ValueError("AUDIT_INDEPENDENCE_NOT_REVIEWED")
                if a["discovery_diff_count"]:
                    raise ValueError("INDEPENDENT_DISCOVERY_MISMATCH")
                if a["challenge_count"] < context.minimum_audit_challenges:
                    raise ValueError("AUDIT_CHALLENGE_INSUFFICIENT")
                if a["challenge_passed"] > a["challenge_count"]:
                    raise ValueError("AUDIT_CHALLENGE_COUNTS_INVALID")
                if a["challenge_passed"] != a["challenge_count"]:
                    failed.append(eid + ":AUDIT_CHALLENGE_FAILED")
            if p["kind"] == "proof":
                if not all(report["proof_checks"].values()):
                    raise ValueError("FORMAL_STATEMENT_AXIOM_BINDING_OR_CHECKER_UNVERIFIED")
            if p["kind"] == "mutation":
                m = report["mutation_checks"]
                if m["unknown"]:
                    raise ValueError("MUTATION_UNKNOWN")
                if (m["invalid"] or m["equivalent"]) and not m["exclusions_reviewed"]:
                    raise ValueError("MUTATION_EXCLUSIONS_UNREVIEWED")
                denominator = m["killed"] + m["survived"] + m["unknown"]
                if denominator == 0:
                    raise ValueError("MUTATION_EMPTY_DENOMINATOR")
                if m["must_kill_survived"]:
                    failed.append(eid + ":CRITICAL_MUTANT_SURVIVED")
                if m["killed"] * 10000 < context.min_mutation_score_basis_points * denominator:
                    failed.append(eid + ":MUTATION_GATE_FAILED")
            verified.append(eid)
            if p["status"] == "FAIL":
                failed.append(eid + ":VERIFIED_FAILURE")
            elif p["status"] == "INCONCLUSIVE":
                uncertain.append(eid + ":VERIFIED_INCONCLUSIVE")
            for finding in report["findings"]:
                if finding["state"] == "OPEN" and finding["severity"] in {"critical", "high"}:
                    failed.append(eid + ":OPEN_HIGH_RISK_FINDING:" + finding["id"])
            for r in report["results"]:
                if r["status"] == "FAIL":
                    failed.append(eid + ":CASE_FAILED:" + r["case_id"])
                elif r["status"] == "INCONCLUSIVE" or r["assertions"] == 0:
                    uncertain.append(eid + ":CASE_NOT_VERIFIED:" + r["case_id"])
                elif p["status"] == "PASS":
                    satisfied.add((r["obligation_id"], r["case_id"]))
        except (ValueError, TypeError, KeyError, InvalidSignature, RecursionError, UnicodeError) as exc:
            uncertain.append(eid + ":EVIDENCE_REJECTED:" + (str(exc) or type(exc).__name__))
    if expected - satisfied:
        uncertain.append("REQUIRED_CASE_EVIDENCE_MISSING")
    if failed:
        return _decision("FAIL", request_hash, failed + uncertain, verified)
    if uncertain:
        return _decision("INCONCLUSIVE", request_hash, uncertain, verified)
    return _decision("PASS", request_hash, ["REFERENCE_PROFILE_REQUIREMENTS_SATISFIED"], verified)
