"""Trusted, tenant-scoped runtime boundary for the local parity harness.

Request-serving code may select only a server-owned runner by identity.  It
cannot submit a command, callable, corpus, metrics, measurement evidence, or
thresholds.  Those objects are installed in an immutable allowlist at service
composition time and are bound to one exact tenant, project and authenticated
principal.

The underlying harness produces local engineering evidence only.  This service
registers every generated CAS object to the tenant, adds an exact project
reference, and persists the report through :class:`ParityMetadataRepository`.
It never upgrades local or synthetic evidence to external evidence and never
emits a certification decision.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any, cast

from .canonical import digest_of, require_digest, sha256_bytes
from .cas import ContentAddressableStore
from .db.store import IdempotencyClaim, MetadataStore
from .enums import ArtifactStorageState, ValidationLevel
from .errors import ContractViolation, CorruptObject, IdempotencyConflict, NotFound
from .parity import MANDATORY_SCENARIOS, EvidenceBinding, ParityDecision, ParityThresholds
from .parity_harness import (
    EvidenceClass,
    MeasurementBundle,
    ParityHarnessResult,
    ParityScenarioHarness,
    ScenarioCorpus,
    ScenarioExecution,
    ScenarioExecutor,
    ScenarioRequest,
)
from .parity_store import ParityMetadataRepository
from .security import Ed25519ProvenanceSigner, ProvenanceSigner, SignedStatement

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}$")
_OPERATION = "cache-parity-trusted-harness/v1.2"
_RECEIPT_KIND = "elmos.cache-parity-harness-service-result/v1.2"

PARITY_HARNESS_REF_SOURCE_KIND = "parity-harness-report"


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(
            f"{field_name} must be a bounded identifier",
            field=field_name,
        )
    return value


def parity_harness_ref_kind(project_id: str) -> str:
    """Return the exact project-qualified reference used for every artifact."""

    return f"project:{_identifier(project_id, 'project_id')}"


@dataclass(frozen=True, slots=True)
class ParityHarnessRunRequest:
    """The complete caller-controlled request surface (and nothing else)."""

    tenant_id: str
    project_id: str
    runner_id: str
    report_id: str

    def __post_init__(self) -> None:
        for field_name in ("tenant_id", "project_id", "runner_id", "report_id"):
            _identifier(getattr(self, field_name), field_name)

    def to_dict(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "runner_id": self.runner_id,
            "report_id": self.report_id,
        }


@dataclass(frozen=True)
class TrustedScenarioExecutor:
    """Server-owned executor plus its immutable implementation identity."""

    identity: str
    evidence_class: EvidenceClass
    implementation_digest: str
    executor: ScenarioExecutor = field(repr=False)

    def __post_init__(self) -> None:
        _identifier(self.identity, "executor identity")
        require_digest(self.implementation_digest)
        self.validate()

    def validate(self) -> None:
        """Recheck the server-owned object before it can cross the run boundary."""

        if not callable(self.executor):
            raise ContractViolation("trusted scenario executor must be callable")
        if self.executor.identity != self.identity:
            raise ContractViolation("trusted executor identity does not match its registration")
        if self.executor.evidence_class is not self.evidence_class:
            raise ContractViolation("trusted executor evidence class does not match its registration")

    def __call__(self, request: ScenarioRequest) -> ScenarioExecution:
        return self.executor(request)

    def identity_document(self) -> dict[str, str]:
        return {
            "identity": self.identity,
            "evidence_class": str(self.evidence_class),
            "implementation_digest": self.implementation_digest,
        }


@dataclass(frozen=True)
class TrustedParityRunnerRegistration:
    """One exact server-owned runner allowlist entry."""

    tenant_id: str
    project_id: str
    principal_id: str
    runner_id: str
    corpus: ScenarioCorpus
    binding: EvidenceBinding
    measurements: MeasurementBundle
    executors: Mapping[str, TrustedScenarioExecutor]
    signer: ProvenanceSigner = field(repr=False)
    thresholds: ParityThresholds = field(default_factory=ParityThresholds)

    def __post_init__(self) -> None:
        for field_name in ("tenant_id", "project_id", "principal_id", "runner_id"):
            _identifier(getattr(self, field_name), field_name)

        frozen_executors = MappingProxyType(dict(self.executors))
        object.__setattr__(self, "executors", frozen_executors)
        expected = set(MANDATORY_SCENARIOS)
        actual = set(frozen_executors)
        if actual != expected:
            raise ContractViolation(
                "trusted runner requires the exact mandatory executor set",
                missing=sorted(expected - actual),
                unexpected=sorted(actual - expected),
            )
        if self.binding.corpus_digest != self.corpus.digest:
            raise ContractViolation("trusted runner corpus does not match its evidence binding")
        expected_scope = digest_of({"tenant_id": self.tenant_id, "project_id": self.project_id})
        if (
            not self.binding.authenticated
            or self.binding.tenant_scope_digest != expected_scope
            or self.binding.authorization_digest is None
        ):
            raise ContractViolation("trusted runner requires an exact authenticated tenant scope")
        if self.measurements.producer_identity != self.binding.executor_identity:
            raise ContractViolation("trusted measurement producer does not match its binding")
        for scenario_id, executor in frozen_executors.items():
            if not isinstance(executor, TrustedScenarioExecutor):
                raise ContractViolation(
                    "trusted runner registry accepts only bound executor registrations",
                    scenario_id=scenario_id,
                )
            if executor.identity != self.binding.executor_identity:
                raise ContractViolation(
                    "trusted scenario executor does not match its binding",
                    scenario_id=scenario_id,
                )
            if executor.evidence_class is not self.measurements.evidence_class:
                raise ContractViolation(
                    "trusted scenario and measurement evidence classes cannot be mixed",
                    scenario_id=scenario_id,
                )
        if not isinstance(self.signer, Ed25519ProvenanceSigner):
            raise ContractViolation("trusted parity reports require an Ed25519 signer")
        # Accessing the key here also rejects a verify-only signer before any run.
        _identifier(self.signer.active_key_id, "signing key id")

    @property
    def registration_digest(self) -> str:
        for executor in self.executors.values():
            executor.validate()
        measurement_evidence = [
            {
                "role": item.role,
                "media_type": item.media_type,
                "digest": sha256_bytes(item.content),
                "size": len(item.content),
            }
            for item in self.measurements.raw_evidence
        ]
        measurement = {
            "measurement_id": self.measurements.measurement_id,
            "producer_identity": self.measurements.producer_identity,
            "evidence_class": str(self.measurements.evidence_class),
            "global_metrics": dict(self.measurements.global_metrics),
            "cohorts": {name: dict(values) for name, values in sorted(self.measurements.cohorts.items())},
            "raw_evidence": measurement_evidence,
            "replay": self.measurements.replay.to_dict(),
        }
        return digest_of(
            {
                "schema_version": "1.2.0",
                "kind": "elmos.cache-parity-trusted-runner-registration/v1.2",
                "tenant_id": self.tenant_id,
                "project_id": self.project_id,
                "principal_id": self.principal_id,
                "runner_id": self.runner_id,
                "corpus": self.corpus.to_dict(),
                "binding": self.binding.to_dict(),
                "measurement": measurement,
                "executors": {
                    scenario_id: executor.identity_document()
                    for scenario_id, executor in sorted(self.executors.items())
                },
                "thresholds": asdict(self.thresholds),
                "signer": {
                    "algorithm": self.signer.algorithm,
                    "key_id": self.signer.active_key_id,
                },
            }
        )


class TrustedParityRunnerRegistry:
    """Closed allowlist populated only while composing the server."""

    def __init__(self, registrations: Sequence[TrustedParityRunnerRegistration]) -> None:
        entries: dict[
            tuple[str, str, str],
            tuple[TrustedParityRunnerRegistration, str],
        ] = {}
        for registration in registrations:
            key = (
                registration.tenant_id,
                registration.project_id,
                registration.runner_id,
            )
            registration_digest = registration.registration_digest
            previous = entries.get(key)
            if previous is not None:
                if previous[1] != registration_digest:
                    raise IdempotencyConflict(
                        "trusted parity runner ID has conflicting registrations",
                        runner_id=registration.runner_id,
                    )
                raise ContractViolation(
                    "trusted parity runner registration is duplicated",
                    runner_id=registration.runner_id,
                )
            entries[key] = (registration, registration_digest)
        self._entries = MappingProxyType(entries)

    def resolve(
        self,
        request: ParityHarnessRunRequest,
        *,
        authenticated_principal_id: str,
    ) -> TrustedParityRunnerRegistration:
        _identifier(authenticated_principal_id, "authenticated_principal_id")
        entry = self._entries.get((request.tenant_id, request.project_id, request.runner_id))
        if entry is None or entry[0].principal_id != authenticated_principal_id:
            # Deliberately make missing, foreign-scope and foreign-principal
            # outcomes indistinguishable and side-effect free.
            raise NotFound("trusted parity runner is unavailable")
        registration, installed_digest = entry
        if registration.registration_digest != installed_digest:
            raise ContractViolation("trusted parity runner registration drifted after install")
        return registration


@dataclass(frozen=True)
class ParityHarnessArtifact:
    digest: str
    size_bytes: int
    media_type: str
    artifact_kind: str

    def __post_init__(self) -> None:
        require_digest(self.digest)
        if (
            not isinstance(self.size_bytes, int)
            or isinstance(self.size_bytes, bool)
            or self.size_bytes < 1
            or not isinstance(self.media_type, str)
            or not self.media_type
            or not isinstance(self.artifact_kind, str)
            or not self.artifact_kind
        ):
            raise ContractViolation("parity harness artifact metadata is incomplete")

    def to_dict(self) -> dict[str, Any]:
        return {
            "digest": self.digest,
            "size_bytes": self.size_bytes,
            "media_type": self.media_type,
            "artifact_kind": self.artifact_kind,
        }


@dataclass(frozen=True)
class ParityHarnessServiceResult:
    """Durable service receipt; never external evidence or certification."""

    tenant_id: str
    project_id: str
    runner_id: str
    report_id: str
    registration_digest: str
    report: Mapping[str, Any]
    evidence_class: EvidenceClass
    measurement_manifest_digest: str
    scenario_manifest_digests: Mapping[str, str]
    report_artifact_digest: str
    signature_artifact_digest: str
    artifacts: tuple[ParityHarnessArtifact, ...]
    replayed: bool = False

    def __post_init__(self) -> None:
        for field_name in ("tenant_id", "project_id", "runner_id", "report_id"):
            _identifier(getattr(self, field_name), field_name)
        require_digest(self.registration_digest)
        require_digest(self.measurement_manifest_digest)
        require_digest(self.report_artifact_digest)
        require_digest(self.signature_artifact_digest)
        if set(self.scenario_manifest_digests) != set(MANDATORY_SCENARIOS):
            raise ContractViolation("parity service result requires every scenario manifest")
        for digest in self.scenario_manifest_digests.values():
            require_digest(digest)
        artifact_digests = tuple(artifact.digest for artifact in self.artifacts)
        if not artifact_digests or len(set(artifact_digests)) != len(artifact_digests):
            raise ContractViolation("parity service result artifacts must be non-empty and unique")

    @property
    def external_evidence_state(self) -> str:
        return "NOT_RUN"

    @property
    def certification_state(self) -> str:
        return "NOT_CERTIFIED"

    def receipt(self) -> dict[str, Any]:
        return {
            "schema_version": "1.2.0",
            "kind": _RECEIPT_KIND,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "runner_id": self.runner_id,
            "report_id": self.report_id,
            "registration_digest": self.registration_digest,
            "report": dict(self.report),
            "evidence_class": str(self.evidence_class),
            "measurement_manifest_digest": self.measurement_manifest_digest,
            "scenario_manifest_digests": dict(sorted(self.scenario_manifest_digests.items())),
            "report_artifact_digest": self.report_artifact_digest,
            "signature_artifact_digest": self.signature_artifact_digest,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "external_evidence_state": self.external_evidence_state,
            "maximum_local_decision": str(ParityDecision.READY_FOR_EXTERNAL_GATE),
            "certification_state": self.certification_state,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.receipt(), "idempotent_replay": self.replayed}


class TrustedParityHarnessService:
    """Execute an allowlisted harness and make its local artifacts durable."""

    def __init__(
        self,
        *,
        cas: ContentAddressableStore,
        repository: ParityMetadataRepository,
        registry: TrustedParityRunnerRegistry,
    ) -> None:
        self.cas = cas
        self.repository = repository
        self.store: MetadataStore = repository.store
        self.registry = registry

    def execute(
        self,
        request: ParityHarnessRunRequest,
        *,
        authenticated_principal_id: str,
    ) -> ParityHarnessServiceResult:
        if type(request) is not ParityHarnessRunRequest:
            raise ContractViolation("trusted parity service requires the closed request type")
        registration = self.registry.resolve(
            request,
            authenticated_principal_id=authenticated_principal_id,
        )
        self._require_persisted_scope(request)
        claim_request = {
            **request.to_dict(),
            "principal_id": authenticated_principal_id,
            "registration_digest": registration.registration_digest,
        }
        idempotency_key = self._idempotency_key(request)
        with self.store.transaction():
            claim = self.store.claim_idempotent(
                request.tenant_id,
                idempotency_key,
                _OPERATION,
                claim_request,
            )
        if claim.replayed:
            result = self._result_from_receipt(
                claim,
                request=request,
                registration=registration,
            )
            self._verify_durable_result(result, registration)
            return result

        if not claim.claimed or claim.owner_token is None:
            raise ContractViolation("trusted parity idempotency claim is invalid")

        harness = ParityScenarioHarness(
            cas=self.cas,
            corpus=registration.corpus,
            executors=dict(registration.executors),
        )
        harness_result = harness.run(
            report_id=request.report_id,
            binding=registration.binding,
            measurements=registration.measurements,
            thresholds=registration.thresholds,
            signer=registration.signer,
        )
        if harness_result.signed_report is None:
            raise ContractViolation("trusted parity harness did not sign its report")
        registration.signer.verify_statement(harness_result.signed_report)
        artifacts = self._collect_artifacts(harness_result)
        self._register_artifacts(request, registration, artifacts)

        report_document = harness_result.report.to_dict()
        self.repository.put_parity_report(
            request.tenant_id,
            request.project_id,
            request.report_id,
            report_document,
        )
        if harness_result.signature_artifact_digest is None:
            raise ContractViolation("trusted parity harness did not produce a signature artifact")
        result = ParityHarnessServiceResult(
            tenant_id=request.tenant_id,
            project_id=request.project_id,
            runner_id=request.runner_id,
            report_id=request.report_id,
            registration_digest=registration.registration_digest,
            report=report_document,
            evidence_class=harness_result.evidence_class,
            measurement_manifest_digest=harness_result.measurement_manifest_digest,
            scenario_manifest_digests=harness_result.scenario_manifest_digests,
            report_artifact_digest=harness_result.report_artifact_digest,
            signature_artifact_digest=harness_result.signature_artifact_digest,
            artifacts=artifacts,
        )
        with self.store.transaction():
            self.store.complete_idempotent(
                request.tenant_id,
                idempotency_key,
                _OPERATION,
                claim_request,
                claim.owner_token,
                claim.fence,
                result.receipt(),
            )
        return result

    def _require_persisted_scope(self, request: ParityHarnessRunRequest) -> None:
        row = self.store.query_one(
            "SELECT tenant_id FROM projects WHERE project_id=?",
            (request.project_id,),
        )
        if row is None or str(row[0]) != request.tenant_id:
            # Runner registration is not authority to create a tenant/project.
            raise NotFound("trusted parity runner is unavailable")

    @staticmethod
    def _idempotency_key(request: ParityHarnessRunRequest) -> str:
        return "parity-harness:" + digest_of(
            {
                "tenant_id": request.tenant_id,
                "project_id": request.project_id,
                "report_id": request.report_id,
            }
        )

    def _collect_artifacts(
        self,
        result: ParityHarnessResult,
    ) -> tuple[ParityHarnessArtifact, ...]:
        if result.signature_artifact_digest is None or result.signed_report is None:
            raise ContractViolation("trusted parity harness requires a signed report artifact")
        signature_document = self._document(result.signature_artifact_digest)
        if signature_document != result.signed_report.to_dict():
            raise ContractViolation("parity signature artifact is not bound to its report")
        return self._collect_artifact_graph(
            report_id=result.report.report_id,
            report=result.report.to_dict(),
            evidence_class=result.evidence_class,
            measurement_manifest_digest=result.measurement_manifest_digest,
            scenario_manifest_digests=result.scenario_manifest_digests,
            report_artifact_digest=result.report_artifact_digest,
            signature_artifact_digest=result.signature_artifact_digest,
        )

    def _collect_artifact_graph(
        self,
        *,
        report_id: str,
        report: Mapping[str, Any],
        evidence_class: EvidenceClass,
        measurement_manifest_digest: str,
        scenario_manifest_digests: Mapping[str, str],
        report_artifact_digest: str,
        signature_artifact_digest: str,
    ) -> tuple[ParityHarnessArtifact, ...]:
        artifacts: dict[str, ParityHarnessArtifact] = {}
        if (
            report.get("report_id") != report_id
            or report.get("decision")
            not in {
                str(ParityDecision.NOT_RUN),
                str(ParityDecision.FAILED),
                str(ParityDecision.READY_FOR_EXTERNAL_GATE),
            }
            or report.get("claim_policy") != "measured_only_external_gate_required"
        ):
            raise ContractViolation("parity service report identity or claim policy is invalid")

        def add(
            digest: str,
            *,
            media_type: str,
            artifact_kind: str,
            declared_size: int | None = None,
        ) -> None:
            normalized = require_digest(digest)
            raw = self.cas.get_bytes(normalized, verify=True)
            if not raw or (declared_size is not None and len(raw) != declared_size):
                raise CorruptObject(
                    "parity harness artifact size does not match its manifest",
                    digest=normalized,
                )
            candidate = ParityHarnessArtifact(
                normalized,
                len(raw),
                media_type,
                artifact_kind,
            )
            previous = artifacts.get(normalized)
            if previous is not None and previous != candidate:
                raise ContractViolation(
                    "one parity CAS object has conflicting artifact metadata",
                    digest=normalized,
                )
            artifacts[normalized] = candidate

        def add_raw(document: Mapping[str, Any]) -> tuple[str, ...]:
            raw_evidence = document.get("raw_evidence")
            if not isinstance(raw_evidence, list):
                raise ContractViolation("parity harness manifest raw evidence is missing")
            roles: set[str] = set()
            digests: list[str] = []
            for item in raw_evidence:
                if not isinstance(item, Mapping) or set(item) != {
                    "role",
                    "media_type",
                    "digest",
                    "size",
                }:
                    raise ContractViolation("parity harness raw evidence entry is invalid")
                media_type = item["media_type"]
                role = item["role"]
                digest = item["digest"]
                size = item["size"]
                if (
                    not isinstance(role, str)
                    or not role
                    or role in roles
                    or not isinstance(media_type, str)
                    or not media_type
                    or not isinstance(digest, str)
                    or not isinstance(size, int)
                    or isinstance(size, bool)
                    or size < 1
                ):
                    raise ContractViolation("parity harness raw evidence metadata is invalid")
                roles.add(role)
                digests.append(digest)
                add(
                    digest,
                    media_type=media_type,
                    artifact_kind="cache-parity-raw-evidence",
                    declared_size=size,
                )
            return tuple(digests)

        binding = report.get("binding")
        metrics = report.get("metrics")
        cohorts = report.get("cohorts")
        if not isinstance(binding, Mapping):
            raise ContractViolation("parity report evidence binding is missing")
        measurement = self._document(measurement_manifest_digest)
        if (
            measurement.get("kind") != "elmos.cache-parity-measurement-bundle/v1.2"
            or measurement.get("binding") != dict(binding)
            or measurement.get("producer_identity") != binding.get("executor_identity")
            or measurement.get("evidence_class") != str(evidence_class)
            or measurement.get("external_evidence_state") != "NOT_RUN"
            or measurement.get("global_metrics") != metrics
            or measurement.get("cohorts") != cohorts
        ):
            raise ContractViolation("parity measurement manifest kind is invalid")
        measurement_raw = add_raw(measurement)
        if not measurement_raw:
            raise ContractViolation("parity measurement manifest requires raw evidence")
        add(
            measurement_manifest_digest,
            media_type="application/json",
            artifact_kind="cache-parity-measurement-manifest",
        )

        if set(scenario_manifest_digests) != set(MANDATORY_SCENARIOS):
            raise ContractViolation("parity result does not contain the exact scenario manifests")
        report_scenarios_value = report.get("scenarios")
        if not isinstance(report_scenarios_value, list):
            raise ContractViolation("parity report scenarios are missing")
        report_scenarios: dict[str, Mapping[str, Any]] = {}
        for scenario in report_scenarios_value:
            if not isinstance(scenario, Mapping) or not isinstance(scenario.get("scenario_id"), str):
                raise ContractViolation("parity report scenario is invalid")
            report_scenarios[str(scenario["scenario_id"])] = scenario
        if len(report_scenarios) != len(report_scenarios_value) or set(report_scenarios) != set(MANDATORY_SCENARIOS):
            raise ContractViolation("parity report does not contain the exact scenario set")
        for scenario_id, digest in sorted(scenario_manifest_digests.items()):
            manifest = self._document(digest)
            request = manifest.get("request")
            request_digest = manifest.get("request_digest")
            if (
                manifest.get("kind") != "elmos.cache-parity-scenario-execution/v1.2"
                or manifest.get("scenario_id") != scenario_id
                or manifest.get("executor_identity") != binding.get("executor_identity")
                or manifest.get("evidence_class") != str(evidence_class)
                or manifest.get("external_evidence_state") != "NOT_RUN"
                or not isinstance(request, Mapping)
                or not isinstance(request_digest, str)
                or request_digest != digest_of(dict(request))
                or request.get("run_id") != report_id
                or request.get("binding") != dict(binding)
                or request.get("measurement_bundle_digest") != measurement_manifest_digest
            ):
                raise ContractViolation(
                    "parity scenario manifest identity is invalid",
                    scenario_id=scenario_id,
                )
            raw_digests = add_raw(manifest)
            add(
                digest,
                media_type="application/json",
                artifact_kind="cache-parity-scenario-manifest",
            )
            report_scenario = report_scenarios[scenario_id]
            evidence_digests = report_scenario.get("evidence_digests")
            detail = report_scenario.get("detail")
            replay = manifest.get("replay")
            status = manifest.get("status")
            if (
                not isinstance(evidence_digests, list)
                or any(not isinstance(item, str) for item in evidence_digests)
                or sorted(evidence_digests) != sorted((*raw_digests, digest))
                or not isinstance(detail, Mapping)
                or report_scenario.get("status") != status
                or detail.get("execution_manifest_digest") != digest
                or detail.get("measurement_bundle_digest") != measurement_manifest_digest
                or (
                    status == "PASS"
                    and (
                        not raw_digests
                        or not isinstance(replay, Mapping)
                        or replay.get("request_digest") != request_digest
                    )
                )
            ):
                raise ContractViolation(
                    "parity report scenario is not bound to its artifact graph",
                    scenario_id=scenario_id,
                )

        report_envelope = self._document(report_artifact_digest)
        if (
            report_envelope.get("kind") != "elmos.cache-parity-harness-report/v1.2"
            or report_envelope.get("report") != dict(report)
            or report_envelope.get("evidence_class") != str(evidence_class)
            or report_envelope.get("measurement_manifest_digest") != measurement_manifest_digest
            or report_envelope.get("scenario_manifest_digests") != dict(sorted(scenario_manifest_digests.items()))
            or report_envelope.get("external_evidence_state") != "NOT_RUN"
            or report_envelope.get("maximum_local_decision") != str(ParityDecision.READY_FOR_EXTERNAL_GATE)
        ):
            raise ContractViolation("parity harness report artifact is not bound to its report")
        add(
            report_artifact_digest,
            media_type="application/json",
            artifact_kind="cache-parity-harness-report",
        )

        signature_document = self._document(signature_artifact_digest)
        if set(signature_document) != {
            "kind",
            "statement",
            "signature",
            "key_id",
            "algorithm",
        }:
            raise ContractViolation("parity signature artifact shape is invalid")
        try:
            signed = SignedStatement.from_dict(signature_document)
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractViolation("parity signature artifact is invalid") from exc
        if (
            signed.kind != "elmos.cache-parity-report/v1.2"
            or signed.statement != dict(report)
            or signed.algorithm != "ed25519"
        ):
            raise ContractViolation("parity signature artifact is not bound to its report")
        add(
            signature_artifact_digest,
            media_type="application/json",
            artifact_kind="cache-parity-report-signature",
        )
        return tuple(artifacts[digest] for digest in sorted(artifacts))

    def _document(self, digest: str) -> dict[str, Any]:
        document = self.cas.get_document(digest)
        if not isinstance(document, dict):
            raise ContractViolation("parity harness CAS manifest must be a JSON object")
        return cast(dict[str, Any], document)

    def _register_artifacts(
        self,
        request: ParityHarnessRunRequest,
        registration: TrustedParityRunnerRegistration,
        artifacts: Sequence[ParityHarnessArtifact],
    ) -> None:
        ref_kind = parity_harness_ref_kind(request.project_id)
        metadata = {
            "project_id": request.project_id,
            "report_id": request.report_id,
            "runner_id": request.runner_id,
            "registration_digest": registration.registration_digest,
            "evidence_class": str(registration.measurements.evidence_class),
            "external_evidence_state": "NOT_RUN",
            "certification_state": "NOT_CERTIFIED",
        }
        with self.store.transaction():
            for artifact in artifacts:
                existing = self.store.get_artifact(request.tenant_id, artifact.digest)
                if existing is not None and (
                    existing.size_bytes != artifact.size_bytes
                    or existing.media_type != artifact.media_type
                    or existing.storage_state
                    in {
                        ArtifactStorageState.QUARANTINED,
                        ArtifactStorageState.DELETING,
                        ArtifactStorageState.DELETED,
                    }
                    or existing.validation_level is ValidationLevel.QUARANTINED
                ):
                    raise ContractViolation(
                        "existing tenant artifact registration conflicts with parity evidence",
                        digest=artifact.digest,
                    )
                self.store.register_artifact(
                    request.tenant_id,
                    artifact.digest,
                    artifact.size_bytes,
                    artifact.media_type,
                    artifact.artifact_kind,
                    ArtifactStorageState.LOCAL,
                    ValidationLevel.UNVERIFIED,
                    metadata,
                )
                self.store.add_artifact_ref(
                    request.tenant_id,
                    PARITY_HARNESS_REF_SOURCE_KIND,
                    request.report_id,
                    artifact.digest,
                    ref_kind,
                )

    def _result_from_receipt(
        self,
        claim: IdempotencyClaim,
        *,
        request: ParityHarnessRunRequest,
        registration: TrustedParityRunnerRegistration,
    ) -> ParityHarnessServiceResult:
        receipt = claim.response
        expected_keys = {
            "schema_version",
            "kind",
            "tenant_id",
            "project_id",
            "runner_id",
            "report_id",
            "registration_digest",
            "report",
            "evidence_class",
            "measurement_manifest_digest",
            "scenario_manifest_digests",
            "report_artifact_digest",
            "signature_artifact_digest",
            "artifacts",
            "external_evidence_state",
            "maximum_local_decision",
            "certification_state",
        }
        if not isinstance(receipt, Mapping) or set(receipt) != expected_keys:
            raise CorruptObject("stored parity harness idempotency receipt is invalid")
        if (
            receipt.get("schema_version") != "1.2.0"
            or receipt.get("kind") != _RECEIPT_KIND
            or receipt.get("tenant_id") != request.tenant_id
            or receipt.get("project_id") != request.project_id
            or receipt.get("runner_id") != request.runner_id
            or receipt.get("report_id") != request.report_id
            or receipt.get("registration_digest") != registration.registration_digest
            or receipt.get("external_evidence_state") != "NOT_RUN"
            or receipt.get("maximum_local_decision") != str(ParityDecision.READY_FOR_EXTERNAL_GATE)
            or receipt.get("certification_state") != "NOT_CERTIFIED"
        ):
            raise CorruptObject("stored parity harness receipt binding is invalid")
        report = receipt.get("report")
        manifests = receipt.get("scenario_manifest_digests")
        artifact_items = receipt.get("artifacts")
        if (
            not isinstance(report, Mapping)
            or not isinstance(manifests, Mapping)
            or not isinstance(artifact_items, list)
        ):
            raise CorruptObject("stored parity harness receipt payload is invalid")
        evidence_class_value = receipt.get("evidence_class")
        measurement_digest = receipt.get("measurement_manifest_digest")
        report_artifact_digest = receipt.get("report_artifact_digest")
        signature_artifact_digest = receipt.get("signature_artifact_digest")
        if (
            not isinstance(evidence_class_value, str)
            or not isinstance(measurement_digest, str)
            or not isinstance(report_artifact_digest, str)
            or not isinstance(signature_artifact_digest, str)
        ):
            raise CorruptObject("stored parity harness receipt digest fields are invalid")
        try:
            evidence_class = EvidenceClass(evidence_class_value)
            parsed_artifacts: list[ParityHarnessArtifact] = []
            for item in artifact_items:
                if not isinstance(item, Mapping) or set(item) != {
                    "digest",
                    "size_bytes",
                    "media_type",
                    "artifact_kind",
                }:
                    raise ContractViolation("stored parity artifact receipt is malformed")
                digest = item["digest"]
                size_bytes = item["size_bytes"]
                media_type = item["media_type"]
                artifact_kind = item["artifact_kind"]
                if (
                    not isinstance(digest, str)
                    or not isinstance(size_bytes, int)
                    or isinstance(size_bytes, bool)
                    or not isinstance(media_type, str)
                    or not isinstance(artifact_kind, str)
                ):
                    raise ContractViolation("stored parity artifact receipt types are invalid")
                parsed_artifacts.append(
                    ParityHarnessArtifact(
                        digest=digest,
                        size_bytes=size_bytes,
                        media_type=media_type,
                        artifact_kind=artifact_kind,
                    )
                )
            artifacts = tuple(parsed_artifacts)
            scenario_manifests: dict[str, str] = {}
            for scenario_id, digest in manifests.items():
                if not isinstance(scenario_id, str) or not isinstance(digest, str):
                    raise ContractViolation("stored scenario manifest receipt types are invalid")
                scenario_manifests[scenario_id] = require_digest(digest)
            result = ParityHarnessServiceResult(
                tenant_id=request.tenant_id,
                project_id=request.project_id,
                runner_id=request.runner_id,
                report_id=request.report_id,
                registration_digest=registration.registration_digest,
                report=dict(report),
                evidence_class=evidence_class,
                measurement_manifest_digest=require_digest(measurement_digest),
                scenario_manifest_digests=scenario_manifests,
                report_artifact_digest=require_digest(report_artifact_digest),
                signature_artifact_digest=require_digest(signature_artifact_digest),
                artifacts=artifacts,
                replayed=True,
            )
        except (KeyError, TypeError, ValueError, ContractViolation) as exc:
            raise CorruptObject("stored parity harness receipt fields are invalid") from exc
        if set(scenario_manifests) != set(MANDATORY_SCENARIOS):
            raise CorruptObject("stored parity harness receipt is incomplete")
        return result

    def _verify_durable_result(
        self,
        result: ParityHarnessServiceResult,
        registration: TrustedParityRunnerRegistration,
    ) -> None:
        persisted = self.repository.get_parity_report(
            result.tenant_id,
            result.project_id,
            result.report_id,
        )
        if persisted != dict(result.report):
            raise CorruptObject("persisted parity report does not match its service receipt")
        try:
            graph_artifacts = self._collect_artifact_graph(
                report_id=result.report_id,
                report=result.report,
                evidence_class=result.evidence_class,
                measurement_manifest_digest=result.measurement_manifest_digest,
                scenario_manifest_digests=result.scenario_manifest_digests,
                report_artifact_digest=result.report_artifact_digest,
                signature_artifact_digest=result.signature_artifact_digest,
            )
        except ContractViolation as exc:
            raise CorruptObject("persisted parity artifact graph is invalid") from exc
        if graph_artifacts != result.artifacts:
            raise CorruptObject("stored parity receipt does not enumerate its exact artifact graph")
        expected_ref = (
            PARITY_HARNESS_REF_SOURCE_KIND,
            result.report_id,
            parity_harness_ref_kind(result.project_id),
        )
        for artifact in result.artifacts:
            raw = self.cas.get_bytes(artifact.digest, verify=True)
            owned = self.store.get_artifact(result.tenant_id, artifact.digest)
            if (
                len(raw) != artifact.size_bytes
                or owned is None
                or owned.size_bytes != artifact.size_bytes
                or owned.media_type != artifact.media_type
                or owned.storage_state
                in {
                    ArtifactStorageState.QUARANTINED,
                    ArtifactStorageState.DELETING,
                    ArtifactStorageState.DELETED,
                }
                or owned.validation_level is ValidationLevel.QUARANTINED
                or expected_ref not in self.store.artifact_referrers(result.tenant_id, artifact.digest)
            ):
                raise CorruptObject(
                    "parity harness artifact ownership is incomplete",
                    digest=artifact.digest,
                )
        signature = SignedStatement.from_dict(self._document(result.signature_artifact_digest))
        if signature.statement != dict(result.report):
            raise CorruptObject("parity report signature does not bind the persisted report")
        registration.signer.verify_statement(signature)


__all__ = [
    "PARITY_HARNESS_REF_SOURCE_KIND",
    "ParityHarnessArtifact",
    "ParityHarnessRunRequest",
    "ParityHarnessServiceResult",
    "TrustedParityHarnessService",
    "TrustedParityRunnerRegistration",
    "TrustedParityRunnerRegistry",
    "TrustedScenarioExecutor",
    "parity_harness_ref_kind",
]
