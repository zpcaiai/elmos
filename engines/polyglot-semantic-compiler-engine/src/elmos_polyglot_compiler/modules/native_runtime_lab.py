"""Batch P native-lab obligations and host-bound receipt validation."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Mapping, Optional

from ..contracts import ContractError, ExecutionAuthority, RuntimeRequest
from ..evidence import validate_evidence_receipt
from ..models import (
    BatchType,
    EvidenceState,
    ObligationStatus,
    SemanticObligation,
    SemanticRisk,
)


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_text(value: Any, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    if len(value.encode("utf-8")) > maximum:
        raise ValueError(f"{label} exceeds the bounded size")
    return value


class NativeRuntimeLabModule:
    """Defines lab profiles; it never executes commands or mints evidence."""

    def __init__(self) -> None:
        # These are declarative profile identities, not claims about installed
        # versions, operating systems, images, or runtime availability.
        self.toolchains: Dict[str, Dict[str, str]] = {
            "openjdk21": {
                "profile_id": "openjdk21",
                "runtime_family": "JVM",
                "configuration_state": "DECLARED",
            },
            "dotnet8": {
                "profile_id": "dotnet8",
                "runtime_family": "CLR",
                "configuration_state": "DECLARED",
            },
            "rust_stable": {
                "profile_id": "rust_stable",
                "runtime_family": "NATIVE",
                "configuration_state": "DECLARED",
            },
            "clang18": {
                "profile_id": "clang18",
                "runtime_family": "NATIVE",
                "configuration_state": "DECLARED",
            },
        }

    @staticmethod
    def expected_evidence_type(execution_id: str) -> str:
        _require_text(execution_id, "execution_id", maximum=160)
        return f"native-runtime/{execution_id}"

    def attest_lab_execution(
        self,
        toolchain_key: str,
        command: str,
        exit_code: int,
        *,
        evidence_receipt: Optional[Mapping[str, Any]] = None,
        request: Optional[RuntimeRequest] = None,
        authority: Optional[ExecutionAuthority] = None,
    ) -> Dict[str, Any]:
        """Validate evidence for an execution performed outside this module.

        ``exit_code`` is a requested/claimed binding only. It is not treated as
        an observed result unless the exact execution subject is covered by a
        host-verified receipt.
        """

        toolchain_key = _require_text(toolchain_key, "toolchain_key", maximum=64)
        command = _require_text(command, "command", maximum=1_048_576)
        if toolchain_key not in self.toolchains:
            raise ValueError(f"unknown declared toolchain profile: {toolchain_key}")
        if not isinstance(exit_code, int) or isinstance(exit_code, bool):
            raise ValueError("exit_code must be an integer")
        if exit_code < 0 or exit_code > 255:
            raise ValueError("exit_code must be between 0 and 255")

        command_digest = _digest_text(command)
        subject_material = "\0".join(
            (toolchain_key, command_digest, str(exit_code))
        )
        execution_id = (
            "native-"
            + hashlib.sha256(subject_material.encode("utf-8")).hexdigest()[:24]
        )
        subject_digest = _digest_text(subject_material)
        result: Dict[str, Any] = {
            "attestation_id": None,
            "execution_id": execution_id,
            "toolchain": toolchain_key,
            "toolchain_spec": dict(self.toolchains[toolchain_key]),
            "command_digest": command_digest,
            "expected_evidence_type": self.expected_evidence_type(execution_id),
            "subject_digest": subject_digest,
            "observed_exit_code": None,
            "artifact_digest": None,
            "receipt_digest": None,
            "evidence_state": EvidenceState.NOT_RUN.value,
            "status": "NOT_RUN",
            "reason": "HOST_VERIFIED_NATIVE_RECEIPT_REQUIRED",
        }
        if evidence_receipt is None and request is None and authority is None:
            return result
        if evidence_receipt is None or request is None or authority is None:
            result.update(
                status="INVALID",
                evidence_state=EvidenceState.INVALID.value,
                reason="RECEIPT_CONTEXT_INCOMPLETE",
            )
            return result
        if not isinstance(evidence_receipt, Mapping):
            result.update(
                status="INVALID",
                evidence_state=EvidenceState.INVALID.value,
                reason="RECEIPT_CONTRACT_INVALID",
            )
            return result
        if evidence_receipt.get("evidence_type") != result["expected_evidence_type"]:
            result.update(
                status="INVALID",
                evidence_state=EvidenceState.INVALID.value,
                reason="EXECUTION_SUBJECT_MISMATCH",
            )
            return result

        try:
            evidence_state, code, receipt_digest = validate_evidence_receipt(
                evidence_receipt,
                request=request,
                authority=authority,
                expected_subject_digest=subject_digest,
            )
        except (ContractError, TypeError, ValueError):
            result.update(
                status="INVALID",
                evidence_state=EvidenceState.INVALID.value,
                reason="RECEIPT_CONTRACT_INVALID",
            )
            return result

        receipt_status = evidence_receipt.get("status")
        host_verified = (
            receipt_digest is not None
            and receipt_digest in authority.verified_evidence_digests
        )
        result.update(
            attestation_id=evidence_receipt.get("evidence_id"),
            artifact_digest=evidence_receipt.get("artifact_digest"),
            receipt_digest=receipt_digest,
            evidence_state=evidence_state.value,
            reason=code,
        )
        if (
            receipt_status == "PASSED"
            and evidence_state is EvidenceState.INDEPENDENTLY_VERIFIED
            and host_verified
            and exit_code == 0
        ):
            result.update(
                observed_exit_code=exit_code,
                status="ATTESTED",
                reason="HOST_VERIFIED_NATIVE_EXECUTION",
            )
        elif receipt_status == "PASSED" and host_verified and exit_code != 0:
            result.update(
                status="INVALID",
                evidence_state=EvidenceState.INVALID.value,
                reason="PASSED_RECEIPT_HAS_NONZERO_EXIT_CODE",
            )
        elif receipt_status == "FAILED" and host_verified:
            result.update(
                observed_exit_code=exit_code,
                status="FAILED",
                reason="HOST_VERIFIED_NATIVE_FAILURE",
            )
        elif evidence_state is EvidenceState.INVALID:
            result["status"] = "INVALID"
        elif receipt_status == "NOT_RUN":
            result["status"] = "NOT_RUN"
        else:
            result["status"] = "INCONCLUSIVE"
        return result

    def create_runtime_lab_obligation(
        self,
        source_lab: str,
        target_lab: str,
        property_name: str,
    ) -> SemanticObligation:
        """Emit a Batch P obligation without claiming native execution."""

        source_lab = _require_text(source_lab, "source_lab", maximum=512)
        target_lab = _require_text(target_lab, "target_lab", maximum=512)
        property_name = _require_text(property_name, "property_name", maximum=512)
        digest = _digest_text("\0".join((source_lab, target_lab, property_name)))
        return SemanticObligation(
            obligation_id=f"obl-P-{digest.removeprefix('sha256:')[:24]}",
            batch=BatchType.BATCH_P,
            layer="runtime-lab",
            property_name=property_name,
            invariants=("TOOLCHAIN_HERMETICITY", "REAL_NATIVE_EXECUTION_EVIDENCE"),
            input_digest=digest,
            risk=SemanticRisk.CRITICAL,
            status=ObligationStatus.NOT_RUN,
        )
