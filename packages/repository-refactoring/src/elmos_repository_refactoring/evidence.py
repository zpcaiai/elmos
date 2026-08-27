"""Skill 15 — the evidence bundle.

Assembles everything a reviewer, an auditor or a billing system needs, and
makes each claim checkable rather than asserted:

* **Every artifact carries a digest**, and the manifest digest covers the set,
  so a bundle whose contents were edited fails verification.
* **Traceability is complete or the bundle is partial.**  A patch hunk that
  cannot be mapped back to a plan step, a recipe execution and a validation
  reference makes the bundle ``partial`` — it does not quietly omit the hunk.
* **A model narrative is never evidence.**  Only machine-produced artifacts
  with digests and tool provenance enter the bundle.
* **Redaction preserves non-repudiation.**  Redacted content is replaced by its
  digest, so the fact that *this exact content* existed remains provable.
* **A signature is optional; pretending to have one is not.**  Without a
  signing key the bundle is emitted unsigned and says so.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from .contracts import (
    ContractError,
    GateOutcome,
    isoformat_utc,
    merge_digests,
    require_digest,
    sha256_bytes,
    sha256_payload,
    utc_now,
)

BUNDLE_KIND = "EvidenceBundle"
API_VERSION = "elmos.dev/v1"

#: Retention classes, ordered from shortest to longest life.
RETENTION_CLASSES = ("transient", "operational", "audit", "legal-hold")


@dataclass(frozen=True, slots=True)
class Artifact:
    artifact_id: str
    type: str
    uri: str
    digest: str
    size_bytes: int
    media_type: str = "application/json"
    retention_class: str = "audit"
    redacted: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "artifactId": self.artifact_id,
            "type": self.type,
            "uri": self.uri,
            "digest": self.digest,
            "sizeBytes": self.size_bytes,
            "mediaType": self.media_type,
            "retentionClass": self.retention_class,
            "redacted": self.redacted,
        }


@dataclass(frozen=True, slots=True)
class TraceabilityEntry:
    patch_hunk_id: str
    step_id: str
    recipe_execution_id: str
    validation_refs: tuple[str, ...]
    symbol_ids: tuple[str, ...] = ()
    action_ids: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return bool(self.step_id and self.recipe_execution_id and self.validation_refs)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "patchHunkId": self.patch_hunk_id,
            "stepId": self.step_id,
            "recipeExecutionId": self.recipe_execution_id,
            "validationRefs": list(self.validation_refs),
        }
        if self.symbol_ids:
            payload["symbolIds"] = list(self.symbol_ids)
        if self.action_ids:
            payload["actionIds"] = list(self.action_ids)
        return payload


@dataclass(frozen=True, slots=True)
class GateDecisionRecord:
    gate: str
    decision: GateOutcome
    evidence_refs: tuple[str, ...]
    waiver_approval_id: str = ""

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "gate": self.gate,
            "decision": self.decision.value,
            "evidenceRefs": list(self.evidence_refs),
        }
        if self.waiver_approval_id:
            payload["waiverApprovalId"] = self.waiver_approval_id
        return payload


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    analysis_usd: Decimal = Decimal("0")
    transform_usd: Decimal = Decimal("0")
    verification_usd: Decimal = Decimal("0")
    repair_usd: Decimal = Decimal("0")
    wall_clock_seconds: int = 0

    @property
    def total_usd(self) -> Decimal:
        return self.analysis_usd + self.transform_usd + self.verification_usd + self.repair_usd

    def to_payload(self) -> dict[str, Any]:
        return {
            "analysisUsd": str(self.analysis_usd),
            "transformUsd": str(self.transform_usd),
            "verificationUsd": str(self.verification_usd),
            "repairUsd": str(self.repair_usd),
            "totalUsd": str(self.total_usd),
            "wallClockSeconds": self.wall_clock_seconds,
        }


@dataclass(frozen=True, slots=True)
class BundleInputs:
    request_digest: str
    plan_digest: str
    policy_digest: str
    recipe_lock_digest: str
    snapshot_digests: Mapping[str, str]
    toolchain_digests: tuple[str, ...] = ()
    adapter_digests: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "requestDigest": self.request_digest,
            "planDigest": self.plan_digest,
            "policyDigest": self.policy_digest,
            "recipeLockDigest": self.recipe_lock_digest,
            "snapshotDigests": dict(sorted(self.snapshot_digests.items())),
        }
        if self.toolchain_digests:
            payload["toolchainDigests"] = list(self.toolchain_digests)
        if self.adapter_digests:
            payload["adapterDigests"] = list(self.adapter_digests)
        return payload


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    bundle_id: str
    run_id: str
    created_at: datetime
    inputs: BundleInputs
    artifacts: tuple[Artifact, ...]
    traceability: tuple[TraceabilityEntry, ...]
    gate_decisions: tuple[GateDecisionRecord, ...]
    approvals: tuple[Mapping[str, Any], ...] = ()
    cost: CostBreakdown = field(default_factory=CostBreakdown)
    incomplete_reasons: tuple[str, ...] = ()
    signature: Mapping[str, str] | None = None

    @property
    def status(self) -> str:
        if self.incomplete_reasons:
            return "partial"
        if not self.artifacts or not self.traceability:
            return "partial"
        return "complete"

    @property
    def manifest_digest(self) -> str:
        return merge_digests(item.digest for item in self.artifacts) if self.artifacts else sha256_payload({})

    def body(self) -> dict[str, Any]:
        return {
            "apiVersion": API_VERSION,
            "kind": BUNDLE_KIND,
            "bundleId": self.bundle_id,
            "runId": self.run_id,
            "status": self.status,
            "createdAt": isoformat_utc(self.created_at),
            "inputs": self.inputs.to_payload(),
            "artifacts": [item.to_payload() for item in self.artifacts],
            "traceability": [item.to_payload() for item in self.traceability],
            "gateDecisions": [item.to_payload() for item in self.gate_decisions],
            "approvals": [dict(item) for item in self.approvals],
            "cost": self.cost.to_payload(),
            "manifestDigest": self.manifest_digest,
            "incompleteReasons": list(self.incomplete_reasons),
        }

    def to_payload(self) -> dict[str, Any]:
        payload = self.body()
        if self.signature is not None:
            payload["signature"] = dict(self.signature)
        return payload

    @property
    def digest(self) -> str:
        return sha256_payload(self.body())


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def artifact_from_payload(
    artifact_id: str,
    artifact_type: str,
    payload: Any,
    *,
    uri: str = "",
    retention_class: str = "audit",
    redact: bool = False,
) -> Artifact:
    """Register a produced artifact by digesting its canonical encoding."""

    if retention_class not in RETENTION_CLASSES:
        raise ContractError("invalid_retention_class", f"unknown retention class '{retention_class}'")
    from .contracts import canonical_json

    encoded = canonical_json(payload).encode("utf-8")
    return Artifact(
        artifact_id=artifact_id,
        type=artifact_type,
        uri=uri or f"elmos://artifact/{artifact_id}",
        digest=sha256_bytes(encoded),
        size_bytes=len(encoded),
        media_type="application/json",
        retention_class=retention_class,
        redacted=redact,
    )


def artifact_from_text(
    artifact_id: str,
    artifact_type: str,
    text: str,
    *,
    media_type: str = "text/plain",
    uri: str = "",
    retention_class: str = "audit",
    redact: bool = False,
) -> Artifact:
    encoded = text.encode("utf-8")
    return Artifact(
        artifact_id=artifact_id,
        type=artifact_type,
        uri=uri or f"elmos://artifact/{artifact_id}",
        digest=sha256_bytes(encoded),
        size_bytes=len(encoded),
        media_type=media_type,
        retention_class=retention_class,
        redacted=redact,
    )


def build_traceability(
    source_map: Sequence[Mapping[str, Any]],
    *,
    step_id: str,
    recipe_execution_id: str,
    validation_refs: Sequence[str],
) -> tuple[tuple[TraceabilityEntry, ...], tuple[str, ...]]:
    """Map hunks to their origin, and report the ones that cannot be mapped."""

    entries: list[TraceabilityEntry] = []
    unmapped: list[str] = []
    for item in source_map:
        hunk_id = str(item.get("hunkId", ""))
        actions = tuple(str(value) for value in item.get("actionIds", ()))
        symbols = tuple(str(value) for value in item.get("symbols", ()))
        entry = TraceabilityEntry(
            patch_hunk_id=hunk_id,
            step_id=step_id,
            recipe_execution_id=recipe_execution_id if actions else "",
            validation_refs=tuple(validation_refs),
            symbol_ids=symbols,
            action_ids=actions,
        )
        entries.append(entry)
        if not entry.complete:
            unmapped.append(hunk_id or "<unnamed hunk>")
    return tuple(entries), tuple(unmapped)


def assemble(
    *,
    run_id: str,
    inputs: BundleInputs,
    artifacts: Sequence[Artifact],
    source_map: Sequence[Mapping[str, Any]],
    gate_decisions: Sequence[GateDecisionRecord],
    step_id: str,
    recipe_execution_id: str,
    validation_refs: Sequence[str],
    approvals: Sequence[Mapping[str, Any]] = (),
    cost: CostBreakdown | None = None,
    now: datetime | None = None,
    extra_incomplete_reasons: Sequence[str] = (),
) -> EvidenceBundle:
    """Build the bundle and decide honestly whether it is complete."""

    traceability, unmapped = build_traceability(
        source_map,
        step_id=step_id,
        recipe_execution_id=recipe_execution_id,
        validation_refs=validation_refs,
    )
    reasons = list(extra_incomplete_reasons)
    if unmapped:
        reasons.append(
            f"{len(unmapped)} patch hunk(s) could not be traced to a recipe action: " + ", ".join(unmapped[:10])
        )
    if not artifacts:
        reasons.append("no artifacts were registered")
    waived = [
        item.gate
        for item in gate_decisions
        if item.decision is GateOutcome.WAIVED and not item.waiver_approval_id
    ]
    if waived:
        reasons.append("waived gate(s) without a recorded approval: " + ", ".join(waived))

    return EvidenceBundle(
        bundle_id=sha256_payload({"run": run_id, "inputs": inputs.to_payload()})[:24],
        run_id=run_id,
        created_at=now or utc_now(),
        inputs=inputs,
        artifacts=tuple(sorted(artifacts, key=lambda item: item.artifact_id)),
        traceability=traceability,
        gate_decisions=tuple(sorted(gate_decisions, key=lambda item: item.gate)),
        approvals=tuple(approvals),
        cost=cost or CostBreakdown(),
        incomplete_reasons=tuple(dict.fromkeys(reasons)),
    )


# ---------------------------------------------------------------------------
# Signing and verification
# ---------------------------------------------------------------------------


def sign(bundle: EvidenceBundle, *, key_id: str, secret: bytes, algorithm: str = "HMAC-SHA256") -> EvidenceBundle:
    """Sign the bundle body with a host-supplied key.

    HMAC is used because it needs no key infrastructure to verify inside this
    process; a host with real signing keys substitutes its own scheme and keeps
    the same field shape.
    """

    if algorithm != "HMAC-SHA256":
        raise ContractError("unsupported_signature_algorithm", f"unsupported algorithm '{algorithm}'")
    if not secret:
        raise ContractError("empty_signing_key", "a signing key must not be empty")
    from .contracts import canonical_json

    body = canonical_json(bundle.body()).encode("utf-8")
    value = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return EvidenceBundle(
        bundle_id=bundle.bundle_id,
        run_id=bundle.run_id,
        created_at=bundle.created_at,
        inputs=bundle.inputs,
        artifacts=bundle.artifacts,
        traceability=bundle.traceability,
        gate_decisions=bundle.gate_decisions,
        approvals=bundle.approvals,
        cost=bundle.cost,
        incomplete_reasons=bundle.incomplete_reasons,
        signature={"algorithm": algorithm, "keyId": key_id, "value": value},
    )


@dataclass(frozen=True, slots=True)
class VerificationOutcome:
    valid: bool
    reasons: tuple[str, ...]
    signature_checked: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "signatureChecked": self.signature_checked,
            "reasons": list(self.reasons),
        }


def verify_bundle(
    payload: Mapping[str, Any],
    *,
    secret: bytes | None = None,
    expected_artifacts: Mapping[str, str] | None = None,
) -> VerificationOutcome:
    """Independently re-verify a serialised bundle.

    Deliberately works from the payload rather than the object, so it checks
    what was *written out* rather than what is in memory.
    """

    reasons: list[str] = []
    body = {key: value for key, value in payload.items() if key != "signature"}

    artifacts = body.get("artifacts", [])
    if not isinstance(artifacts, list):
        return VerificationOutcome(False, ("artifacts is not a list",))
    digests: list[str] = []
    for item in artifacts:
        if not isinstance(item, Mapping):
            reasons.append("an artifact entry is not an object")
            continue
        try:
            digests.append(require_digest(item.get("digest"), "artifact.digest"))
        except ContractError as error:
            reasons.append(f"artifact '{item.get('artifactId')}': {error.message}")

    declared_manifest = body.get("manifestDigest")
    recomputed = merge_digests(digests) if digests else sha256_payload({})
    if declared_manifest != recomputed:
        reasons.append("manifestDigest does not match the artifact digests it claims to cover")

    if expected_artifacts:
        by_id = {
            str(item.get("artifactId")): str(item.get("digest"))
            for item in artifacts
            if isinstance(item, Mapping)
        }
        for artifact_id, digest in expected_artifacts.items():
            if by_id.get(artifact_id) != digest:
                reasons.append(f"artifact '{artifact_id}' does not match the expected digest")

    traceability = body.get("traceability", [])
    if isinstance(traceability, list):
        incomplete = [
            str(item.get("patchHunkId"))
            for item in traceability
            if isinstance(item, Mapping)
            and not (item.get("stepId") and item.get("recipeExecutionId") and item.get("validationRefs"))
        ]
        if incomplete and body.get("status") == "complete":
            reasons.append(
                f"status is 'complete' but {len(incomplete)} hunk(s) have incomplete traceability"
            )

    signature_checked = False
    signature = payload.get("signature")
    if signature is not None:
        if secret is None:
            reasons.append("bundle carries a signature but no key was supplied to verify it")
        elif not isinstance(signature, Mapping):
            reasons.append("signature is not an object")
        else:
            from .contracts import canonical_json

            expected = hmac.new(secret, canonical_json(body).encode("utf-8"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, str(signature.get("value", ""))):
                reasons.append("signature does not verify against the bundle body")
            else:
                signature_checked = True

    return VerificationOutcome(
        valid=not reasons,
        reasons=tuple(reasons),
        signature_checked=signature_checked,
    )


def audit_timeline(events: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """A reviewer-facing timeline derived from the journal, not narrated."""

    return tuple(
        {
            "sequence": item.get("sequence"),
            "at": item.get("at"),
            "type": item.get("type"),
            "step": item.get("step"),
            "digest": item.get("digest"),
        }
        for item in events
    )


def billing_breakdown(cost: CostBreakdown, *, changed_files: int, gates_run: int) -> dict[str, Any]:
    return {
        **cost.to_payload(),
        "changedFiles": changed_files,
        "gatesRun": gates_run,
        "unitOfAccount": "verified-change",
        "note": (
            "cost is reported per verified change; unverified work is recorded but is not a billable outcome"
        ),
    }


def redact(artifact: Artifact) -> Artifact:
    """Replace an artifact's location with its digest, keeping provability."""

    return Artifact(
        artifact_id=artifact.artifact_id,
        type=artifact.type,
        uri=f"elmos://redacted/{artifact.digest}",
        digest=artifact.digest,
        size_bytes=artifact.size_bytes,
        media_type=artifact.media_type,
        retention_class=artifact.retention_class,
        redacted=True,
    )


__all__ = [
    "API_VERSION",
    "BUNDLE_KIND",
    "RETENTION_CLASSES",
    "Artifact",
    "BundleInputs",
    "CostBreakdown",
    "EvidenceBundle",
    "GateDecisionRecord",
    "TraceabilityEntry",
    "VerificationOutcome",
    "artifact_from_payload",
    "artifact_from_text",
    "assemble",
    "audit_timeline",
    "billing_breakdown",
    "build_traceability",
    "redact",
    "sign",
    "verify_bundle",
]
