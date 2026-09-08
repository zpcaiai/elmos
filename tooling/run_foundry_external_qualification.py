#!/usr/bin/env python3
"""Verify externally issued Foundry evidence and certification receipts.

This command is verify-only.  It never executes a provider, trains or deploys a
model, signs a receipt, or grants certification authority.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Mapping, Sequence

from elmos_foundry.canonical import CanonicalLimits, strict_json_loads
from elmos_foundry.domain import CertificationStatus
from elmos_foundry.external_assurance import (
    CertificationRequest,
    ExternalRunKind,
    ExternalRunRequest,
    IndependentAcceptanceRequest,
)
from elmos_foundry.external_qualification import (
    ExternalTrustStore,
    ProviderEvidenceRequest,
    verify_external_qualification_chain,
)
from elmos_pi_harness.independent_verifier import Ed25519Backend  # type: ignore[import-untyped]


class ExternalQualificationInputError(ValueError):
    pass


def _load(path: Path, *, maximum: int, label: str) -> dict[str, Any]:
    if path.is_symlink():
        raise ExternalQualificationInputError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
        status = resolved.stat()
    except OSError as exc:
        raise ExternalQualificationInputError(f"{label} is unavailable") from exc
    if not resolved.is_file() or status.st_size <= 0 or status.st_size > maximum:
        raise ExternalQualificationInputError(
            f"{label} is empty, oversized, or not a file"
        )
    try:
        value = strict_json_loads(
            resolved.read_bytes(), limits=CanonicalLimits(max_document_bytes=maximum)
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ExternalQualificationInputError(
            f"{label} is not strict UTF-8 JSON"
        ) from exc
    if not isinstance(value, dict):
        raise ExternalQualificationInputError(f"{label} must be an object")
    return value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExternalQualificationInputError(f"{label} must be an object")
    return value


def _exact_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise ExternalQualificationInputError(
            f"{label} fields differ: missing={missing}, extra={extra}"
        )


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ExternalQualificationInputError(f"{label} must be text")
    return value


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ExternalQualificationInputError(f"{label} must be an array")
    return tuple(_text(item, f"{label}[]") for item in value)


def _string_map(value: Any, label: str) -> dict[str, str]:
    raw = _mapping(value, label)
    return {
        _text(key, f"{label}.key"): _text(item, f"{label}.{key}")
        for key, item in raw.items()
    }


def _provider_request(value: Any) -> ProviderEvidenceRequest:
    raw = _mapping(value, "provider_request")
    _exact_fields(
        raw,
        {
            "provider_id",
            "provider_version",
            "executable_digest",
            "request_binding_digest",
            "route_id",
            "route_digest",
            "operation",
            "outputs_digest",
        },
        "provider_request",
    )
    return ProviderEvidenceRequest(
        provider_id=_text(raw.get("provider_id"), "provider_id"),
        provider_version=_text(raw.get("provider_version"), "provider_version"),
        executable_digest=_text(raw.get("executable_digest"), "executable_digest"),
        request_binding_digest=_text(
            raw.get("request_binding_digest"), "request_binding_digest"
        ),
        route_id=_text(raw.get("route_id"), "route_id"),
        route_digest=_text(raw.get("route_digest"), "route_digest"),
        operation=_text(raw.get("operation"), "operation"),
        outputs_digest=_text(raw.get("outputs_digest"), "outputs_digest"),
    )


def _external_run_request(value: Any, expected: ExternalRunKind) -> ExternalRunRequest:
    label = f"{expected.value.lower()}_request"
    raw = _mapping(value, label)
    _exact_fields(
        raw,
        {
            "run_kind",
            "request_id",
            "tenant_id",
            "project_id",
            "target_id",
            "environment_id",
            "provider_id",
            "provider_version",
            "producer_id",
            "configuration_digest",
            "input_digests",
            "required_outputs",
        },
        label,
    )
    try:
        kind = ExternalRunKind(_text(raw.get("run_kind"), "run_kind"))
    except ValueError as exc:
        raise ExternalQualificationInputError("run_kind is unsupported") from exc
    if kind is not expected:
        raise ExternalQualificationInputError(f"expected a {expected.value} request")
    return ExternalRunRequest(
        run_kind=kind,
        request_id=_text(raw.get("request_id"), "request_id"),
        tenant_id=_text(raw.get("tenant_id"), "tenant_id"),
        project_id=_text(raw.get("project_id"), "project_id"),
        target_id=_text(raw.get("target_id"), "target_id"),
        environment_id=_text(raw.get("environment_id"), "environment_id"),
        provider_id=_text(raw.get("provider_id"), "provider_id"),
        provider_version=_text(raw.get("provider_version"), "provider_version"),
        producer_id=_text(raw.get("producer_id"), "producer_id"),
        configuration_digest=_text(
            raw.get("configuration_digest"), "configuration_digest"
        ),
        input_digests=_string_map(raw.get("input_digests"), "input_digests"),
        required_outputs=_strings(raw.get("required_outputs"), "required_outputs"),
    )


def _acceptance_request(value: Any) -> IndependentAcceptanceRequest:
    raw = _mapping(value, "acceptance_request")
    _exact_fields(
        raw,
        {
            "request_id",
            "tenant_id",
            "project_id",
            "target_id",
            "producer_id",
            "executor_ids",
            "evidence_bundle_digest",
            "holdout_corpus_digest",
            "external_receipt_digests",
            "required_gates",
        },
        "acceptance_request",
    )
    return IndependentAcceptanceRequest(
        request_id=_text(raw.get("request_id"), "request_id"),
        tenant_id=_text(raw.get("tenant_id"), "tenant_id"),
        project_id=_text(raw.get("project_id"), "project_id"),
        target_id=_text(raw.get("target_id"), "target_id"),
        producer_id=_text(raw.get("producer_id"), "producer_id"),
        executor_ids=_strings(raw.get("executor_ids"), "executor_ids"),
        evidence_bundle_digest=_text(
            raw.get("evidence_bundle_digest"), "evidence_bundle_digest"
        ),
        holdout_corpus_digest=_text(
            raw.get("holdout_corpus_digest"), "holdout_corpus_digest"
        ),
        external_receipt_digests=_string_map(
            raw.get("external_receipt_digests"), "external_receipt_digests"
        ),
        required_gates=_strings(raw.get("required_gates"), "required_gates"),
    )


def _certification_request(value: Any) -> CertificationRequest:
    raw = _mapping(value, "certification_request")
    _exact_fields(
        raw,
        {
            "request_id",
            "tenant_id",
            "project_id",
            "target_id",
            "requested_level",
            "catalog_digest",
            "implementation_digest",
            "policy_digest",
            "external_receipt_digests",
            "independent_acceptance_digest",
            "producer_id",
            "executor_ids",
            "independent_verifier_id",
        },
        "certification_request",
    )
    return CertificationRequest(
        request_id=_text(raw.get("request_id"), "request_id"),
        tenant_id=_text(raw.get("tenant_id"), "tenant_id"),
        project_id=_text(raw.get("project_id"), "project_id"),
        target_id=_text(raw.get("target_id"), "target_id"),
        requested_level=_text(raw.get("requested_level"), "requested_level"),
        catalog_digest=_text(raw.get("catalog_digest"), "catalog_digest"),
        implementation_digest=_text(
            raw.get("implementation_digest"), "implementation_digest"
        ),
        policy_digest=_text(raw.get("policy_digest"), "policy_digest"),
        external_receipt_digests=_string_map(
            raw.get("external_receipt_digests"), "external_receipt_digests"
        ),
        independent_acceptance_digest=_text(
            raw.get("independent_acceptance_digest"),
            "independent_acceptance_digest",
        ),
        producer_id=_text(raw.get("producer_id"), "producer_id"),
        executor_ids=_strings(raw.get("executor_ids"), "executor_ids"),
        independent_verifier_id=_text(
            raw.get("independent_verifier_id"), "independent_verifier_id"
        ),
    )


def verify_bundle(
    bundle: Mapping[str, Any],
    trust_store: ExternalTrustStore,
    *,
    now: int,
) -> dict[str, Any]:
    expected = {
        "schema_version",
        "provider_request",
        "provider_receipt",
        "training_request",
        "training_receipt",
        "deployment_request",
        "deployment_receipt",
        "acceptance_request",
        "acceptance_receipt",
        "certification_request",
        "certification_receipt",
    }
    if set(bundle) != expected:
        raise ExternalQualificationInputError(
            "external qualification bundle fields differ"
        )
    if bundle.get("schema_version") != "elmos.foundry.external-qualification-bundle.v1":
        raise ExternalQualificationInputError(
            "unsupported external qualification bundle schema"
        )
    certification_receipt = bundle.get("certification_receipt")
    if certification_receipt is not None:
        certification_receipt = _mapping(certification_receipt, "certification_receipt")
    decision = verify_external_qualification_chain(
        provider_request=_provider_request(bundle.get("provider_request")),
        provider_receipt=_mapping(bundle.get("provider_receipt"), "provider_receipt"),
        training_request=_external_run_request(
            bundle.get("training_request"), ExternalRunKind.TRAINING
        ),
        training_receipt=_mapping(bundle.get("training_receipt"), "training_receipt"),
        deployment_request=_external_run_request(
            bundle.get("deployment_request"), ExternalRunKind.DEPLOYMENT
        ),
        deployment_receipt=_mapping(
            bundle.get("deployment_receipt"), "deployment_receipt"
        ),
        acceptance_request=_acceptance_request(bundle.get("acceptance_request")),
        acceptance_receipt=_mapping(
            bundle.get("acceptance_receipt"), "acceptance_receipt"
        ),
        certification_request=_certification_request(
            bundle.get("certification_request")
        ),
        certification_receipt=certification_receipt,
        trust_store=trust_store,
        now=now,
    )
    return {
        "schema_version": "elmos.foundry.external-qualification-decision.v1",
        "external_evidence_status": decision.external_evidence_status,
        "certification_status": decision.certification_status.value,
        "trust_store_digest": trust_store.digest,
        "receipt_digests": dict(decision.receipt_digests),
        "blockers": list(decision.blockers),
        "evaluated_at_epoch": now,
    }


def _write(path: Path, result: Mapping[str, Any]) -> None:
    if path.exists() and path.is_symlink():
        raise ExternalQualificationInputError("output must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--trust-store", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--now", type=int, default=None, help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    now = int(time.time()) if args.now is None else args.now
    if args.bundle is None or args.trust_store is None:
        result: dict[str, Any] = {
            "schema_version": "elmos.foundry.external-qualification-decision.v1",
            "external_evidence_status": "NOT_RUN",
            "certification_status": CertificationStatus.NOT_CERTIFIED.value,
            "trust_store_digest": None,
            "receipt_digests": {},
            "blockers": [
                "external bundle is not configured",
                "external Ed25519 trust store is not configured",
            ],
            "evaluated_at_epoch": now,
        }
        print(json.dumps(result, sort_keys=True))
        return 2
    trust_store_digest: str | None = None
    try:
        trust_document = _load(
            args.trust_store, maximum=1024 * 1024, label="trust store"
        )
        trust_store = ExternalTrustStore.from_mapping(
            trust_document,
            backend=Ed25519Backend(),
        )
        trust_store_digest = trust_store.digest
        bundle = _load(args.bundle, maximum=16 * 1024 * 1024, label="evidence bundle")
        result = verify_bundle(bundle, trust_store, now=now)
        if args.output is not None:
            _write(args.output, result)
    except (ExternalQualificationInputError, TypeError, ValueError) as exc:
        result = {
            "schema_version": "elmos.foundry.external-qualification-decision.v1",
            "external_evidence_status": "REJECTED",
            "certification_status": CertificationStatus.NOT_CERTIFIED.value,
            "trust_store_digest": trust_store_digest,
            "receipt_digests": {},
            "blockers": [str(exc)],
            "evaluated_at_epoch": now,
        }
        print(json.dumps(result, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return (
        0
        if result["certification_status"] == CertificationStatus.CERTIFIED.value
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
