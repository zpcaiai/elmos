"""Production host bindings and external assurance verification.

This module contains the repository-owned part of the external boundary.  It
can execute an exact, digest-pinned provider command and verify externally
issued training, deployment, independent-acceptance and certification
receipts.  It deliberately has no receipt issuer or local signing fallback.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
import signal
import stat
import subprocess
import time
from types import MappingProxyType
from typing import Any

from .adapters import (
    AdapterBinding,
    ExternalAdapterRoute,
    ExternalExecutionBroker,
    InvocationPermit,
    InvocationRequest,
)
from .canonical import (
    canonical_digest,
    canonical_json_bytes,
    canonical_value,
    require_identifier,
    strict_json_loads,
    validate_digest,
)
from .domain import CertificationStatus, TenantScope


class ExternalAssuranceError(RuntimeError):
    """An external operation or receipt failed closed."""


class ExternalRunKind(str, Enum):
    PROVIDER = "PROVIDER"
    TRAINING = "TRAINING"
    DEPLOYMENT = "DEPLOYMENT"


SignatureVerifier = Callable[[str, str, str, str], bool]
REQUIRED_EXTERNAL_STAGES = frozenset({"PROVIDER", "TRAINING", "DEPLOYMENT"})


def _digest_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _identifiers(values: Sequence[str], label: str) -> tuple[str, ...]:
    normalized = tuple(values)
    if not normalized or normalized != tuple(sorted(set(normalized))):
        raise ValueError(f"{label} must be non-empty, unique, and sorted")
    for value in normalized:
        require_identifier(value, label)
    return normalized


def _digest_map(values: Mapping[str, str], label: str) -> Mapping[str, str]:
    normalized = canonical_value(values)
    if not isinstance(normalized, dict) or not normalized:
        raise ValueError(f"{label} must be a non-empty object")
    result: dict[str, str] = {}
    for key, value in normalized.items():
        require_identifier(key, f"{label}.key")
        result[key] = validate_digest(value, f"{label}.{key}")
    return MappingProxyType(result)


def _external_receipts(values: Mapping[str, str]) -> Mapping[str, str]:
    result = _digest_map(values, "external_receipt_digests")
    if set(result) != REQUIRED_EXTERNAL_STAGES:
        raise ValueError("external receipts must cover PROVIDER, TRAINING, and DEPLOYMENT")
    return result


def _unsigned_receipt(document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in document.items() if key not in {"receipt_digest", "signature"}
    }


def _verify_signed_receipt(
    document: Mapping[str, Any],
    *,
    verifier: SignatureVerifier,
    authority_field: str,
) -> str:
    normalized = canonical_value(document)
    if not isinstance(normalized, dict):
        raise ExternalAssuranceError("receipt must be a canonical object")
    claimed = normalized.get("receipt_digest")
    validate_digest(claimed, "receipt_digest")
    actual = canonical_digest(_unsigned_receipt(normalized))
    if claimed != actual:
        raise ExternalAssuranceError("receipt digest does not match its canonical body")
    authority_id = require_identifier(normalized.get(authority_field), authority_field)
    key_id = require_identifier(normalized.get("key_id"), "key_id")
    signature = normalized.get("signature")
    if not isinstance(signature, str) or not signature or len(signature.encode()) > 16_384:
        raise ExternalAssuranceError("receipt signature is missing or unbounded")
    if verifier(authority_id, key_id, actual, signature) is not True:
        raise ExternalAssuranceError("trusted external signature verifier denied the receipt")
    return actual


@dataclass(frozen=True, slots=True)
class ProviderCommandRoute:
    """Exact process route installed by the production host."""

    route_id: str
    route_digest: str
    operation: str
    provider_id: str
    provider_version: str
    executable: Path
    executable_digest: str
    arguments: tuple[str, ...] = ()
    inherited_environment: tuple[str, ...] = ()
    timeout_seconds: float = 300.0
    max_output_bytes: int = 4 * 1024 * 1024

    def __post_init__(self) -> None:
        for value, label in (
            (self.route_id, "route_id"),
            (self.operation, "operation"),
            (self.provider_id, "provider_id"),
            (self.provider_version, "provider_version"),
        ):
            require_identifier(value, label)
        if len(self.route_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.route_digest
        ):
            raise ValueError("route_digest must be 64 lowercase hexadecimal characters")
        validate_digest(self.executable_digest, "executable_digest")
        if not self.executable.is_absolute():
            raise ValueError("provider executable path must be absolute")
        for argument in self.arguments:
            if not isinstance(argument, str) or "\x00" in argument:
                raise ValueError("provider arguments must be NUL-free strings")
        environment = tuple(self.inherited_environment)
        if environment != tuple(sorted(set(environment))):
            raise ValueError("inherited_environment must be unique and sorted")
        for name in environment:
            require_identifier(name, "environment_name")
        if not isinstance(self.timeout_seconds, (int, float)) or not (
            0 < self.timeout_seconds <= 3600
        ):
            raise ValueError("timeout_seconds must be in (0, 3600]")
        if (
            isinstance(self.max_output_bytes, bool)
            or not isinstance(self.max_output_bytes, int)
            or not (1024 <= self.max_output_bytes <= 64 * 1024 * 1024)
        ):
            raise ValueError("max_output_bytes must be between 1 KiB and 64 MiB")

    def public_document(self) -> Mapping[str, Any]:
        return {
            "schema_version": "elmos.foundry.provider-command-route.v1",
            "route_id": self.route_id,
            "route_digest": self.route_digest,
            "operation": self.operation,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "executable": str(self.executable),
            "executable_digest": self.executable_digest,
            "arguments": list(self.arguments),
            "inherited_environment": list(self.inherited_environment),
            "timeout_seconds": self.timeout_seconds,
            "max_output_bytes": self.max_output_bytes,
        }


def build_subprocess_broker(
    *,
    broker_id: str,
    version: str,
    routes: Sequence[ProviderCommandRoute],
    receipt_verifier: SignatureVerifier,
) -> ExternalExecutionBroker:
    """Build a shell-free broker for exact digest-pinned provider commands."""

    if not callable(receipt_verifier):
        raise TypeError("receipt_verifier must be callable")
    route_map = {route.route_id: route for route in routes}
    if not route_map or len(route_map) != len(routes):
        raise ValueError("provider command routes must be non-empty and unique")
    broker_document = {
        "schema_version": "elmos.foundry.subprocess-broker.v1",
        "broker_id": broker_id,
        "version": version,
        "routes": [
            route.public_document() for route in sorted(routes, key=lambda row: row.route_id)
        ],
    }
    broker_digest = canonical_digest(broker_document).removeprefix("sha256:")

    def command_route(route: ExternalAdapterRoute) -> ProviderCommandRoute:
        configured = route_map.get(route.route_id)
        if configured is None:
            raise ExternalAssuranceError("provider command route is not allowlisted")
        path = configured.executable
        try:
            status = path.lstat()
        except OSError as exc:
            raise ExternalAssuranceError("provider executable is unavailable") from exc
        if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
            raise ExternalAssuranceError("provider executable must be a regular non-symlink file")
        if status.st_mode & stat.S_IWOTH:
            raise ExternalAssuranceError("provider executable must not be world-writable")
        if not os.access(path, os.X_OK):
            raise ExternalAssuranceError("provider executable is not executable")
        if _digest_file(path) != configured.executable_digest:
            raise ExternalAssuranceError("provider executable digest drifted")
        if route.digest != configured.route_digest or route.operation != configured.operation:
            raise ExternalAssuranceError("runtime route differs from the pinned command route")
        return configured

    def execute(
        route: ExternalAdapterRoute,
        binding: AdapterBinding,
        request: InvocationRequest,
        permit: InvocationPermit,
        payload: Mapping[str, Any],
        scope: TenantScope,
    ) -> Mapping[str, Any]:
        configured = command_route(route)
        if request.broker_digest != broker_digest:
            raise ExternalAssuranceError("request targets a different broker configuration")
        if request.route_id != configured.route_id or permit.route_id != configured.route_id:
            raise ExternalAssuranceError("request or permit targets a different command route")
        if canonical_digest(payload) != request.payload_digest:
            raise ExternalAssuranceError("provider payload differs from the authorized request")
        envelope = {
            "schema_version": "elmos.foundry.provider-command-request.v1",
            "broker": {
                "broker_id": broker_id,
                "version": version,
                "digest": broker_digest,
            },
            "provider": {
                "provider_id": configured.provider_id,
                "provider_version": configured.provider_version,
                "executable_digest": configured.executable_digest,
            },
            "route": {
                "route_id": route.route_id,
                "route_digest": route.digest,
                "operation": route.operation,
            },
            "binding": {
                "adapter_id": binding.adapter_id,
                "adapter_version": binding.version,
                "adapter_digest": binding.digest,
            },
            "request": request.binding_document(),
            "request_binding_digest": request.binding_digest,
            "permit_id": permit.permit_id,
            "authorization_id": permit.authorization_id,
            "scope_binding_digest": scope.binding_digest,
            "payload": payload,
        }
        environment = {
            name: os.environ[name]
            for name in configured.inherited_environment
            if name in os.environ
        }
        try:
            process = subprocess.Popen(
                [str(configured.executable), *configured.arguments],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                shell=False,
                start_new_session=os.name == "posix",
            )
        except OSError as exc:
            raise ExternalAssuranceError(
                "provider command could not start; no effect was confirmed"
            ) from exc
        try:
            stdout, stderr = process.communicate(
                canonical_json_bytes(envelope), timeout=float(configured.timeout_seconds)
            )
        except subprocess.TimeoutExpired as exc:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            finally:
                process.communicate()
            raise ExternalAssuranceError("provider command timed out with unknown outcome") from exc
        if _digest_file(configured.executable) != configured.executable_digest:
            raise ExternalAssuranceError("provider executable changed during execution")
        if len(stdout) > configured.max_output_bytes:
            raise ExternalAssuranceError("provider stdout exceeds the configured limit")
        if len(stderr) > configured.max_output_bytes:
            raise ExternalAssuranceError("provider stderr exceeds the configured limit")
        if process.returncode != 0:
            raise ExternalAssuranceError(
                f"provider command exited nonzero with unknown outcome: {process.returncode}"
            )
        try:
            response = strict_json_loads(stdout)
        except (TypeError, ValueError) as exc:
            raise ExternalAssuranceError(
                "provider command returned invalid canonical JSON"
            ) from exc
        if not isinstance(response, dict):
            raise ExternalAssuranceError("provider command response must be an object")
        return response

    def verify_result(
        route: ExternalAdapterRoute,
        _binding: AdapterBinding,
        request: InvocationRequest,
        _permit: InvocationPermit,
        result: Mapping[str, Any],
        _scope: TenantScope,
    ) -> bool:
        configured = command_route(route)
        receipt = result.get("provider_receipt")
        if not isinstance(receipt, Mapping):
            return False
        expected = {
            "schema_version": "elmos.foundry.provider-receipt.v1",
            "provider_id": configured.provider_id,
            "provider_version": configured.provider_version,
            "executable_digest": configured.executable_digest,
            "request_binding_digest": request.binding_digest,
            "route_id": route.route_id,
            "route_digest": route.digest,
            "operation": route.operation,
            "outcome": "CONFIRMED",
            "outputs_digest": canonical_digest(result.get("outputs")),
        }
        if any(receipt.get(key) != value for key, value in expected.items()):
            return False
        try:
            _verify_signed_receipt(
                receipt,
                verifier=receipt_verifier,
                authority_field="provider_id",
            )
        except (TypeError, ValueError, ExternalAssuranceError):
            return False
        return True

    return ExternalExecutionBroker(
        broker_id=broker_id,
        version=version,
        digest=broker_digest,
        execute=execute,
        verify_result=verify_result,
    )


@dataclass(frozen=True, slots=True)
class ExternalRunRequest:
    """Exact provider request for a training or deployment run."""

    run_kind: ExternalRunKind
    request_id: str
    tenant_id: str
    project_id: str
    target_id: str
    environment_id: str
    provider_id: str
    provider_version: str
    producer_id: str
    configuration_digest: str
    input_digests: Mapping[str, str]
    required_outputs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.run_kind not in {ExternalRunKind.TRAINING, ExternalRunKind.DEPLOYMENT}:
            raise ValueError("external run request must be TRAINING or DEPLOYMENT")
        for name in (
            "request_id",
            "tenant_id",
            "project_id",
            "target_id",
            "environment_id",
            "provider_id",
            "provider_version",
            "producer_id",
        ):
            require_identifier(getattr(self, name), name)
        validate_digest(self.configuration_digest, "configuration_digest")
        object.__setattr__(self, "input_digests", _digest_map(self.input_digests, "input_digests"))
        object.__setattr__(
            self, "required_outputs", _identifiers(self.required_outputs, "required_outputs")
        )
        mandatory_inputs = {
            ExternalRunKind.TRAINING: {"base-model", "dataset"},
            ExternalRunKind.DEPLOYMENT: {"artifact", "release"},
        }[self.run_kind]
        mandatory_outputs = {
            ExternalRunKind.TRAINING: {"lineage", "metrics", "model"},
            ExternalRunKind.DEPLOYMENT: {"deployment", "health", "rollback"},
        }[self.run_kind]
        if not mandatory_inputs.issubset(self.input_digests):
            raise ValueError(f"{self.run_kind.value} request lacks mandatory input digests")
        if not mandatory_outputs.issubset(self.required_outputs):
            raise ValueError(f"{self.run_kind.value} request lacks mandatory output contracts")

    def binding_document(self) -> Mapping[str, Any]:
        return {
            "schema_version": "elmos.foundry.external-run-request.v1",
            "run_kind": self.run_kind.value,
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "target_id": self.target_id,
            "environment_id": self.environment_id,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "producer_id": self.producer_id,
            "configuration_digest": self.configuration_digest,
            "input_digests": dict(self.input_digests),
            "required_outputs": list(self.required_outputs),
        }

    @property
    def binding_digest(self) -> str:
        return canonical_digest(self.binding_document())


def verify_external_run_receipt(
    request: ExternalRunRequest,
    receipt: Mapping[str, Any],
    *,
    verifier: SignatureVerifier,
) -> str:
    """Verify one reconciled provider receipt and return its canonical digest."""

    expected = {
        "schema_version": "elmos.foundry.external-run-receipt.v1",
        "run_kind": request.run_kind.value,
        "request_id": request.request_id,
        "request_binding_digest": request.binding_digest,
        "tenant_id": request.tenant_id,
        "project_id": request.project_id,
        "target_id": request.target_id,
        "environment_id": request.environment_id,
        "provider_id": request.provider_id,
        "provider_version": request.provider_version,
        "outcome": "CONFIRMED",
        "reconciliation_status": "RECONCILED",
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ExternalAssuranceError("external run receipt does not match its exact request")
    executor_id = require_identifier(receipt.get("executor_id"), "executor_id")
    if executor_id == request.producer_id:
        raise ExternalAssuranceError("external executor must be distinct from the producer")
    outputs = receipt.get("output_digests")
    if not isinstance(outputs, Mapping):
        raise ExternalAssuranceError("external run receipt lacks output digests")
    normalized_outputs = _digest_map(outputs, "output_digests")
    if set(normalized_outputs) != set(request.required_outputs):
        raise ExternalAssuranceError("external run receipt violates the required output contract")
    started_at, finished_at = receipt.get("started_at"), receipt.get("finished_at")
    if (
        isinstance(started_at, bool)
        or not isinstance(started_at, int)
        or isinstance(finished_at, bool)
        or not isinstance(finished_at, int)
        or started_at <= 0
        or finished_at < started_at
    ):
        raise ExternalAssuranceError("external run receipt has an invalid time interval")
    return _verify_signed_receipt(receipt, verifier=verifier, authority_field="provider_id")


@dataclass(frozen=True, slots=True)
class IndependentAcceptanceRequest:
    request_id: str
    tenant_id: str
    project_id: str
    target_id: str
    producer_id: str
    executor_ids: tuple[str, ...]
    evidence_bundle_digest: str
    holdout_corpus_digest: str
    external_receipt_digests: Mapping[str, str]
    required_gates: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("request_id", "tenant_id", "project_id", "target_id", "producer_id"):
            require_identifier(getattr(self, name), name)
        object.__setattr__(self, "executor_ids", _identifiers(self.executor_ids, "executor_ids"))
        object.__setattr__(
            self, "required_gates", _identifiers(self.required_gates, "required_gates")
        )
        for value, label in (
            (self.evidence_bundle_digest, "evidence_bundle_digest"),
            (self.holdout_corpus_digest, "holdout_corpus_digest"),
        ):
            validate_digest(value, label)
        object.__setattr__(
            self,
            "external_receipt_digests",
            _external_receipts(self.external_receipt_digests),
        )

    def binding_document(self) -> Mapping[str, Any]:
        return {
            "schema_version": "elmos.foundry.independent-acceptance-request.v1",
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "target_id": self.target_id,
            "producer_id": self.producer_id,
            "executor_ids": list(self.executor_ids),
            "evidence_bundle_digest": self.evidence_bundle_digest,
            "holdout_corpus_digest": self.holdout_corpus_digest,
            "external_receipt_digests": dict(self.external_receipt_digests),
            "required_gates": list(self.required_gates),
        }

    @property
    def binding_digest(self) -> str:
        return canonical_digest(self.binding_document())


def verify_independent_acceptance(
    request: IndependentAcceptanceRequest,
    receipt: Mapping[str, Any],
    *,
    verifier: SignatureVerifier,
) -> str:
    expected = {
        "schema_version": "elmos.foundry.independent-acceptance-receipt.v1",
        "request_id": request.request_id,
        "request_binding_digest": request.binding_digest,
        "tenant_id": request.tenant_id,
        "project_id": request.project_id,
        "target_id": request.target_id,
        "evidence_bundle_digest": request.evidence_bundle_digest,
        "holdout_corpus_digest": request.holdout_corpus_digest,
        "external_receipt_digests": dict(request.external_receipt_digests),
        "verdict": "PASS",
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ExternalAssuranceError("independent acceptance receipt does not match its request")
    verifier_id = require_identifier(receipt.get("verifier_id"), "verifier_id")
    if verifier_id in {request.producer_id, *request.executor_ids}:
        raise ExternalAssuranceError("independent verifier is not organizationally separate")
    gate_results = receipt.get("gate_results")
    if not isinstance(gate_results, Mapping) or set(gate_results) != set(request.required_gates):
        raise ExternalAssuranceError("independent receipt does not cover every required gate")
    if any(value != "PASS" for value in gate_results.values()):
        raise ExternalAssuranceError("independent receipt contains a non-passing gate")
    if receipt.get("skipped_cases") != [] or receipt.get("unknown_cases") != []:
        raise ExternalAssuranceError("skipped or unknown acceptance cases cannot pass")
    return _verify_signed_receipt(receipt, verifier=verifier, authority_field="verifier_id")


@dataclass(frozen=True, slots=True)
class CertificationRequest:
    request_id: str
    tenant_id: str
    project_id: str
    target_id: str
    requested_level: str
    catalog_digest: str
    implementation_digest: str
    policy_digest: str
    external_receipt_digests: Mapping[str, str]
    independent_acceptance_digest: str
    producer_id: str
    executor_ids: tuple[str, ...]
    independent_verifier_id: str

    def __post_init__(self) -> None:
        for name in (
            "request_id",
            "tenant_id",
            "project_id",
            "target_id",
            "requested_level",
            "producer_id",
            "independent_verifier_id",
        ):
            require_identifier(getattr(self, name), name)
        for value, label in (
            (self.catalog_digest, "catalog_digest"),
            (self.implementation_digest, "implementation_digest"),
            (self.policy_digest, "policy_digest"),
            (self.independent_acceptance_digest, "independent_acceptance_digest"),
        ):
            validate_digest(value, label)
        object.__setattr__(
            self,
            "external_receipt_digests",
            _external_receipts(self.external_receipt_digests),
        )
        object.__setattr__(self, "executor_ids", _identifiers(self.executor_ids, "executor_ids"))
        if self.independent_verifier_id in {self.producer_id, *self.executor_ids}:
            raise ValueError("certification request does not bind an independent verifier")

    def binding_document(self) -> Mapping[str, Any]:
        return {
            "schema_version": "elmos.foundry.certification-request.v1",
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "target_id": self.target_id,
            "requested_level": self.requested_level,
            "catalog_digest": self.catalog_digest,
            "implementation_digest": self.implementation_digest,
            "policy_digest": self.policy_digest,
            "external_receipt_digests": dict(self.external_receipt_digests),
            "independent_acceptance_digest": self.independent_acceptance_digest,
            "producer_id": self.producer_id,
            "executor_ids": list(self.executor_ids),
            "independent_verifier_id": self.independent_verifier_id,
        }

    @property
    def binding_digest(self) -> str:
        return canonical_digest(self.binding_document())


@dataclass(frozen=True, slots=True)
class CertificationDecision:
    status: CertificationStatus
    receipt_digest: str | None = None
    blockers: tuple[str, ...] = field(default_factory=tuple)


def evaluate_certification(
    request: CertificationRequest,
    receipt: Mapping[str, Any] | None,
    *,
    verifier: SignatureVerifier,
    revoked_authorities: Sequence[str] = (),
    now: int | None = None,
) -> CertificationDecision:
    """Verify an external authority decision; absence or ambiguity never passes."""

    if receipt is None:
        return CertificationDecision(
            CertificationStatus.NOT_CERTIFIED,
            blockers=("external certification receipt is NOT_RUN",),
        )
    try:
        expected = {
            "schema_version": "elmos.foundry.certification-receipt.v1",
            "request_id": request.request_id,
            "request_binding_digest": request.binding_digest,
            "tenant_id": request.tenant_id,
            "project_id": request.project_id,
            "target_id": request.target_id,
            "certified_level": request.requested_level,
            "catalog_digest": request.catalog_digest,
            "implementation_digest": request.implementation_digest,
            "policy_digest": request.policy_digest,
            "external_receipt_digests": dict(request.external_receipt_digests),
            "independent_acceptance_digest": request.independent_acceptance_digest,
            "decision": "CERTIFIED",
        }
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise ExternalAssuranceError("certification receipt does not match its exact request")
        authority_id = require_identifier(receipt.get("authority_id"), "authority_id")
        disallowed = {request.producer_id, request.independent_verifier_id, *request.executor_ids}
        if authority_id in disallowed:
            raise ExternalAssuranceError("certification authority is not independent")
        if authority_id in set(revoked_authorities):
            raise ExternalAssuranceError("certification authority is revoked")
        issued_at, expires_at = receipt.get("issued_at"), receipt.get("expires_at")
        current = int(time.time()) if now is None else now
        if (
            isinstance(issued_at, bool)
            or not isinstance(issued_at, int)
            or isinstance(expires_at, bool)
            or not isinstance(expires_at, int)
            or issued_at <= 0
            or expires_at <= issued_at
            or current < issued_at
            or current >= expires_at
        ):
            raise ExternalAssuranceError("certification receipt is outside its validity interval")
        trust_epoch = receipt.get("trust_epoch")
        if isinstance(trust_epoch, bool) or not isinstance(trust_epoch, int) or trust_epoch <= 0:
            raise ExternalAssuranceError("certification receipt lacks a valid trust epoch")
        receipt_digest = _verify_signed_receipt(
            receipt, verifier=verifier, authority_field="authority_id"
        )
    except (TypeError, ValueError, ExternalAssuranceError) as exc:
        return CertificationDecision(
            CertificationStatus.NOT_CERTIFIED,
            blockers=(str(exc),),
        )
    return CertificationDecision(CertificationStatus.CERTIFIED, receipt_digest=receipt_digest)


__all__ = [
    "CertificationDecision",
    "CertificationRequest",
    "ExternalAssuranceError",
    "ExternalRunKind",
    "ExternalRunRequest",
    "IndependentAcceptanceRequest",
    "ProviderCommandRoute",
    "SignatureVerifier",
    "build_subprocess_broker",
    "evaluate_certification",
    "verify_external_run_receipt",
    "verify_independent_acceptance",
]
