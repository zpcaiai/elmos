"""Exact v3 Skill and internal component runtime registry.

Sixteen public Skills have separate concrete handlers.  The 96 kernel
components retain their package identities and an honest local/external state;
unsupported external semantics are never routed through a permissive fallback.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence, Type

from .adapters import (
    DECLARED_ADAPTER_REGISTRY,
    AdapterInvocation,
    AdapterRegistry,
)
from .architecture import ArchitectureExtractor
from .domains import DOMAIN_PACKS, DomainPackOrchestrator
from .repository import RepositorySnapshotter, SnapshotLimits
from .semantic import SemanticCompiler, analyze_semantic_gaps
from .transformation import ChangeSet, FileChange, WorkspaceTransformer


@dataclass(frozen=True, slots=True)
class ComponentDescriptor:
    component_id: str
    name: str
    kernel: str
    implementation: str
    implementation_state: str
    external_evidence: str = "NOT_RUN"

    def to_dict(self) -> dict[str, str]:
        return {
            "component_id": self.component_id,
            "name": self.name,
            "kernel": self.kernel,
            "implementation": self.implementation,
            "implementation_state": self.implementation_state,
            "external_evidence": self.external_evidence,
        }


_COMPONENT_NAMES: dict[str, tuple[str, ...]] = {
    "K1": (
        "GoalAggregate", "GoalCommandService", "RevisionSetRegistry", "RequirementGraphCompiler",
        "ObservableContractCompiler", "SpecDeltaCompiler", "AssumptionLedger", "AcceptanceScenarioCompiler",
        "BudgetAndEtaContract", "GoalRiskClassifier", "GoalCheckpointProjection", "GoalChangeImpactAnalyzer",
    ),
    "K2": (
        "RepositorySnapshotter", "BuildSystemDetector", "SymbolGraphBuilder", "TypeGraphBuilder",
        "CallAndDataFlowGraphBuilder", "ConfigurationGraphBuilder", "DataAndMessageGraphBuilder", "RuntimeTraceIngestor",
        "CapabilityLedger", "DynamicBoundaryDetector", "RepositoryRiskMap", "IncrementalInvalidationEngine",
    ),
    "K3": (
        "FrontendRegistry", "LosslessSyntaxLayer", "CompilerSemanticBridge", "RepositoryLinker",
        "TypeAndEffectIR", "ControlDataSSA", "ProtocolStateMachineIR", "DataTransactionIR",
        "FrameworkSemanticModel", "SourceMapAndLineage", "SemanticGapAnalyzer", "ExecutableSemanticsRuntime",
    ),
    "K4": (
        "RoleSeparatedAgentRuntime", "PhaseAwareModelRouter", "ModelCapabilityRegistry", "ContextPlanner",
        "ArtifactMailbox", "ProofPlanner", "InvariantAndLemmaSynthesizer", "CounterexampleReasoner",
        "RepairSynthesizer", "AdversarialReviewer", "AgentArena", "ReasoningProvenanceRecorder",
    ),
    "K5": (
        "TransformationPlanner", "RuleRegistry", "RulePreservationContract", "DeterministicRecipeEngine",
        "BoundedGenerativeTransformer", "ChangeGraph", "WorktreeCoordinator", "SemanticMergeEngine",
        "FixpointController", "DataMigrationPlanner", "CutoverRollbackPlanner", "TransformationCache",
    ),
    "K6": (
        "ProofObligationGraph", "VerifierPortfolioRouter", "StaticVerificationPipeline", "DifferentialExecutionEngine",
        "PropertyMetamorphicFuzzEngine", "SymbolicAndSMTEngine", "ModelCheckingEngine", "ProofAssistantBridge",
        "NonFunctionalVerification", "CounterexampleMinimizer", "CounterexampleToTest", "ProofCacheAndDriftInvalidator",
    ),
    "K7": (
        "DurableWorkflowRuntime", "EnvironmentAuthority", "WorkspaceManager", "SessionTimeline",
        "ExecutionProvenance", "ToolGateway", "PolicyDecisionPoint", "LeaseAndFencing",
        "CheckpointReplayFork", "SideEffectReconciler", "HarnessAdapterSPI", "SchedulerBackpressureFinOps",
    ),
    "K8": (
        "IndependentStopGate", "ProofStatusPolicy", "E0E5GateEvaluator", "P05DeploymentGate",
        "EvidenceBundleSealer", "CompletionCertificateSigner", "CertifiedEnvelopeRegistry", "WaiverGovernance",
        "DriftAndRevocationMonitor", "CommercialGoldenRouteCertifier", "AssuranceReportGenerator", "AuditExport",
    ),
}


def _component_state(kernel: str, index: int) -> str:
    if kernel == "K2" and index == 1:
        return "LOCAL"
    if kernel == "K6" and index == 1:
        return "LOCAL"
    if kernel == "K7" and index in {1, 8, 9, 10}:
        return "LOCAL"
    if kernel == "K4":
        return "ADAPTER_REQUIRED"
    if kernel == "K6":
        return "ADAPTER_REQUIRED" if index != 1 else "LOCAL"
    if kernel == "K8":
        return "PARTIAL"
    return "PARTIAL"


_KERNEL_IMPLEMENTATIONS = {
    "K1": "elmos_proof_harness.skills.GoalSpecificationHandler",
    "K2": "elmos_proof_harness.repository.RepositorySnapshotter",
    "K3": "elmos_proof_harness.semantic.SemanticCompiler",
    "K4": "elmos_proof_harness.skills.AgenticReasoningHandler",
    "K5": "elmos_proof_harness.transformation.WorkspaceTransformer",
    "K6": "elmos_proof_harness.proof_graph.ProofObligationGraph",
    "K7": "elmos_proof_harness.workflow.WorkflowEngine",
    "K8": "elmos_proof_harness.certification.CertificationService",
}


COMPONENT_REGISTRY: dict[str, ComponentDescriptor] = {
    component_id: ComponentDescriptor(
        component_id,
        name,
        kernel,
        _KERNEL_IMPLEMENTATIONS[kernel],
        _component_state(kernel, index),
    )
    for kernel, names in _COMPONENT_NAMES.items()
    for index, name in enumerate(names, 1)
    for component_id in (f"{kernel}-C{index:02d}",)
}

if len(COMPONENT_REGISTRY) != 96:  # import-time invariant, not a test-only assertion
    raise RuntimeError("v3 component registry must contain exactly 96 components")


@dataclass(frozen=True, slots=True)
class SkillDescriptor:
    skill_id: str
    name: str
    kind: str
    owner: str
    dependencies: tuple[str, ...]
    handler: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "kind": self.kind,
            "owner": self.owner,
            "dependencies": list(self.dependencies),
            "handler": self.handler,
        }


_ALL_KERNELS = (
    "elmos-goal-specification-kernel",
    "elmos-repository-intelligence-kernel",
    "elmos-repository-semantic-compiler-kernel",
    "elmos-agentic-reasoning-kernel",
    "elmos-transformation-kernel",
    "elmos-proof-verification-kernel",
    "elmos-harness-runtime-kernel",
    "elmos-certification-kernel",
)


SKILL_REGISTRY: dict[str, SkillDescriptor] = {
    "elmos-goal-specification-kernel": SkillDescriptor("ELMOS-V3-001", "elmos-goal-specification-kernel", "kernel", "K1", (), "GoalSpecificationHandler"),
    "elmos-repository-intelligence-kernel": SkillDescriptor("ELMOS-V3-002", "elmos-repository-intelligence-kernel", "kernel", "K2", ("elmos-goal-specification-kernel",), "RepositoryIntelligenceHandler"),
    "elmos-repository-semantic-compiler-kernel": SkillDescriptor("ELMOS-V3-003", "elmos-repository-semantic-compiler-kernel", "kernel", "K3", ("elmos-repository-intelligence-kernel",), "RepositorySemanticCompilerHandler"),
    "elmos-agentic-reasoning-kernel": SkillDescriptor("ELMOS-V3-004", "elmos-agentic-reasoning-kernel", "kernel", "K4", ("elmos-goal-specification-kernel", "elmos-repository-semantic-compiler-kernel"), "AgenticReasoningHandler"),
    "elmos-transformation-kernel": SkillDescriptor("ELMOS-V3-005", "elmos-transformation-kernel", "kernel", "K5", ("elmos-repository-semantic-compiler-kernel", "elmos-agentic-reasoning-kernel", "elmos-harness-runtime-kernel"), "TransformationHandler"),
    "elmos-proof-verification-kernel": SkillDescriptor("ELMOS-V3-006", "elmos-proof-verification-kernel", "kernel", "K6", ("elmos-repository-semantic-compiler-kernel", "elmos-harness-runtime-kernel"), "ProofVerificationHandler"),
    "elmos-harness-runtime-kernel": SkillDescriptor("ELMOS-V3-007", "elmos-harness-runtime-kernel", "kernel", "K7", (), "HarnessRuntimeHandler"),
    "elmos-certification-kernel": SkillDescriptor("ELMOS-V3-008", "elmos-certification-kernel", "kernel", "K8", ("elmos-goal-specification-kernel", "elmos-proof-verification-kernel", "elmos-harness-runtime-kernel"), "CertificationHandler"),
    "elmos-domain-spring-legacy-modernization": SkillDescriptor("ELMOS-V3-009", "elmos-domain-spring-legacy-modernization", "domain-pack", "spring-modernization", _ALL_KERNELS, "SpringLegacyModernizationHandler"),
    "elmos-domain-cross-language-conversion": SkillDescriptor("ELMOS-V3-010", "elmos-domain-cross-language-conversion", "domain-pack", "cross-language", _ALL_KERNELS, "CrossLanguageConversionHandler"),
    "elmos-domain-multi-language-project-generation": SkillDescriptor("ELMOS-V3-011", "elmos-domain-multi-language-project-generation", "domain-pack", "project-generation", _ALL_KERNELS, "MultiLanguageProjectGenerationHandler"),
    "elmos-domain-sql-dialect-routine-conversion": SkillDescriptor("ELMOS-V3-012", "elmos-domain-sql-dialect-routine-conversion", "domain-pack", "sql-conversion", _ALL_KERNELS, "SqlDialectRoutineConversionHandler"),
    "elmos-domain-repository-refactoring": SkillDescriptor("ELMOS-V3-013", "elmos-domain-repository-refactoring", "domain-pack", "repository-refactoring", _ALL_KERNELS, "RepositoryRefactoringHandler"),
    "elmos-evaluation-trust-gate": SkillDescriptor("ELMOS-V3-014", "elmos-evaluation-trust-gate", "cross-cutting", "platform", _ALL_KERNELS, "EvaluationTrustGateHandler"),
    "elmos-self-improvement-governance": SkillDescriptor("ELMOS-V3-015", "elmos-self-improvement-governance", "cross-cutting", "platform", _ALL_KERNELS, "SelfImprovementGovernanceHandler"),
    "elmos-commercial-operations-finops": SkillDescriptor("ELMOS-V3-016", "elmos-commercial-operations-finops", "cross-cutting", "platform", _ALL_KERNELS, "CommercialOperationsFinOpsHandler"),
}

if len(SKILL_REGISTRY) != 16:
    raise RuntimeError("v3 Skill registry must contain exactly 16 routable Skills")


@dataclass(frozen=True, slots=True)
class SkillExecutionResult:
    skill: str
    status: str
    output: Mapping[str, Any]
    evidence_refs: tuple[str, ...] = ()
    reason: str = ""
    certified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": self.skill,
            "status": self.status,
            "output": dict(self.output),
            "evidence_refs": list(self.evidence_refs),
            "reason": self.reason,
            "certified": self.certified,
        }


@dataclass(slots=True)
class RuntimeDependencies:
    workspace_roots: tuple[Path, ...]
    adapters: AdapterRegistry
    domains: DomainPackOrchestrator
    semantic_compiler: SemanticCompiler
    architecture_extractor: ArchitectureExtractor

    def authorize_workspace(self, candidate: str) -> Path:
        raw = Path(candidate)
        try:
            metadata = raw.lstat()
        except FileNotFoundError:
            raise PermissionError("workspace path is unavailable") from None
        if metadata.st_mode & 0o170000 == 0o120000:
            raise PermissionError("workspace root cannot be a symlink")
        resolved = raw.resolve(strict=True)
        for root in self.workspace_roots:
            if resolved == root or resolved.is_relative_to(root):
                return resolved
        raise PermissionError("workspace is outside configured roots")


class SkillHandler:
    name: str

    def execute(self, payload: Mapping[str, Any], context: Any, runtime: RuntimeDependencies) -> SkillExecutionResult:
        raise NotImplementedError


class GoalSpecificationHandler(SkillHandler):
    name = "elmos-goal-specification-kernel"

    def execute(self, payload: Mapping[str, Any], context: Any, runtime: RuntimeDependencies) -> SkillExecutionResult:
        objective = _required_string(payload, "objective")
        requirements = _string_list(payload.get("requirements", ()), "requirements")
        if not requirements:
            raise ValueError("requirements cannot be empty")
        assumptions = _string_list(payload.get("assumptions", ()), "assumptions")
        revisions = payload.get("revisions", {})
        if not isinstance(revisions, Mapping) or not revisions:
            raise ValueError("revisions must be a non-empty object")
        contract = {
            "objective": objective,
            "requirements": requirements,
            "assumptions": assumptions,
            "revisions": dict(sorted((str(k), str(v)) for k, v in revisions.items())),
            "acceptance_scenarios": _string_list(payload.get("acceptance_scenarios", ()), "acceptance_scenarios"),
        }
        digest = _digest(contract)
        return SkillExecutionResult(self.name, "COMPILED", {**contract, "goal_digest": digest}, (f"goal:sha256:{digest}",))


class RepositoryIntelligenceHandler(SkillHandler):
    name = "elmos-repository-intelligence-kernel"

    def execute(self, payload: Mapping[str, Any], context: Any, runtime: RuntimeDependencies) -> SkillExecutionResult:
        root = runtime.authorize_workspace(_required_string(payload, "repository"))
        limits = _snapshot_limits(payload.get("limits"))
        graph = RepositorySnapshotter(root, limits=limits, ignore_patterns=_string_list(payload.get("ignore_patterns", ()), "ignore_patterns"), include_generated=payload.get("include_generated") is True, include_vendor=payload.get("include_vendor") is True).snapshot()
        return SkillExecutionResult(self.name, "LOCAL_EXECUTED", {"repository": graph.to_dict()}, (graph.snapshot_id,))


class RepositorySemanticCompilerHandler(SkillHandler):
    name = "elmos-repository-semantic-compiler-kernel"

    def execute(self, payload: Mapping[str, Any], context: Any, runtime: RuntimeDependencies) -> SkillExecutionResult:
        root = runtime.authorize_workspace(_required_string(payload, "repository"))
        graph = RepositorySnapshotter(root, limits=_snapshot_limits(payload.get("limits"))).snapshot()
        bundle = runtime.semantic_compiler.compile(graph)
        architecture = runtime.architecture_extractor.extract(graph, bundle)
        status = "LOCAL_EXECUTED" if bundle.completeness["complete"] else "PARTIAL"
        return SkillExecutionResult(self.name, status, {"semantic": bundle.to_dict(), "architecture": architecture.to_dict(), "capabilities": [item.to_dict() for item in runtime.semantic_compiler.capabilities()]}, (graph.snapshot_id, f"semantic:sha256:{bundle.bundle_digest}", f"architecture:sha256:{architecture.graph_digest}"))


class AgenticReasoningHandler(SkillHandler):
    name = "elmos-agentic-reasoning-kernel"

    def execute(self, payload: Mapping[str, Any], context: Any, runtime: RuntimeDependencies) -> SkillExecutionResult:
        source = _required_string(payload, "source_profile")
        target = _required_string(payload, "target_profile")
        gaps = analyze_semantic_gaps(source, target)
        tasks = [
            {
                "task_id": f"proof-task:{gap.id.removeprefix('gap:')}",
                "family": gap.family,
                "policy": gap.policy,
                "required_roles": ["implementer", "verifier"],
                "status": "PLANNED",
            }
            for gap in gaps
        ]
        digest = _digest(tasks)
        return SkillExecutionResult(self.name, "PLANNED", {"semantic_gaps": [gap.to_dict() for gap in gaps], "proof_plan": tasks, "plan_digest": digest, "model_provider_calls": "NOT_RUN"}, (f"proof-plan:sha256:{digest}",))


class TransformationHandler(SkillHandler):
    name = "elmos-transformation-kernel"

    def execute(self, payload: Mapping[str, Any], context: Any, runtime: RuntimeDependencies) -> SkillExecutionResult:
        root = runtime.authorize_workspace(_required_string(payload, "repository"))
        raw_changes = payload.get("changes")
        if not isinstance(raw_changes, list) or not raw_changes:
            raise ValueError("changes must be a non-empty list")
        changes: list[FileChange] = []
        for item in raw_changes:
            if not isinstance(item, Mapping):
                raise ValueError("each change must be an object")
            content: bytes | None
            if item.get("delete") is True:
                content = None
            elif item.get("encoding", "utf-8") == "base64":
                try:
                    content = base64.b64decode(_required_string(item, "content"), validate=True)
                except ValueError as exc:
                    raise ValueError("invalid base64 change content") from exc
            else:
                content = _required_string(item, "content").encode("utf-8")
            changes.append(FileChange(_required_string(item, "path"), item.get("expected_digest") if isinstance(item.get("expected_digest"), str) else None, content, int(item.get("mode", 0o644))))
        change_set = ChangeSet(tuple(changes), _required_string(payload, "reason"), _required_string(payload, "request_id"))
        transformer = WorkspaceTransformer(root)
        plan = transformer.plan(change_set)
        if payload.get("apply") is not True:
            return SkillExecutionResult(self.name, "DRY_RUN", {"plan": plan.to_dict()}, (plan.plan_id,))
        if "workspace.write" not in _context_authority(context):
            raise PermissionError("workspace.write authority is required to apply changes")
        receipt = transformer.apply(change_set)
        return SkillExecutionResult(self.name, "APPLIED", {"plan": plan.to_dict(), "receipt": receipt.to_dict()}, (receipt.receipt_id,))


class ProofVerificationHandler(SkillHandler):
    name = "elmos-proof-verification-kernel"

    def execute(self, payload: Mapping[str, Any], context: Any, runtime: RuntimeDependencies) -> SkillExecutionResult:
        obligations = payload.get("obligations")
        evidence = payload.get("evidence")
        if not isinstance(obligations, list) or not isinstance(evidence, list):
            raise ValueError("obligations and evidence must be lists")
        by_obligation: MutableMapping[str, list[Mapping[str, Any]]] = {}
        for record in evidence:
            if not isinstance(record, Mapping):
                raise ValueError("evidence entries must be objects")
            obligation_id = _required_string(record, "obligation_id")
            by_obligation.setdefault(obligation_id, []).append(record)
        results: list[dict[str, Any]] = []
        for obligation in obligations:
            if not isinstance(obligation, Mapping):
                raise ValueError("obligation entries must be objects")
            obligation_id = _required_string(obligation, "id")
            required = set(_string_list(obligation.get("required_evidence", ()), "required_evidence"))
            syntactically_valid = {
                str(record.get("kind"))
                for record in by_obligation.get(obligation_id, ())
                if record.get("status") == "PASS"
                and _is_sha256(record.get("digest"))
            }
            missing = sorted(required - syntactically_valid)
            results.append(
                {
                    "obligation_id": obligation_id,
                    "status": "LOCAL_INPUT_VALIDATED" if not missing else "NOT_RUN",
                    "missing": missing,
                    "independent_claim_trusted": False,
                }
            )
        locally_valid = bool(results) and all(
            item["status"] == "LOCAL_INPUT_VALIDATED" for item in results
        )
        digest = _digest(results)
        return SkillExecutionResult(
            self.name,
            "LOCAL_INPUT_VALIDATED" if locally_valid else "NOT_RUN",
            {
                "results": results,
                "result_digest": digest,
                "durable_evidence_verification": "NOT_RUN",
                "production_certification": "NOT_CERTIFIED",
            },
            (f"proof-inputs:sha256:{digest}",),
            "payload evidence claims are not trusted; EvidenceService verification is required",
        )


class HarnessRuntimeHandler(SkillHandler):
    name = "elmos-harness-runtime-kernel"

    def execute(self, payload: Mapping[str, Any], context: Any, runtime: RuntimeDependencies) -> SkillExecutionResult:
        invocation = AdapterInvocation(_required_string(payload, "adapter_id"), _required_string(payload, "capability"), payload.get("payload") if isinstance(payload.get("payload"), Mapping) else {}, tuple(_string_list(payload.get("requested_authority", ()), "requested_authority")), float(payload.get("timeout_seconds", 30.0)), str(payload.get("request_id", "")))
        workspace = payload.get("workspace")
        if workspace is not None:
            workspace = str(runtime.authorize_workspace(str(workspace)))
        if payload.get("execute") is not True:
            manifest = next(
                (
                    item
                    for item in runtime.adapters.manifests()
                    if item.adapter_id == invocation.adapter_id
                ),
                None,
            )
            return SkillExecutionResult(
                self.name,
                "PLANNED" if manifest is not None else "UNSUPPORTED",
                {
                    "adapter_id": invocation.adapter_id,
                    "capability": invocation.capability,
                    "request_digest": invocation.request_digest,
                    "manifest_digest": manifest.identity_digest if manifest else None,
                    "external_execution": "NOT_RUN",
                },
                (manifest.identity_digest,) if manifest else (),
                "set execute=true with explicit adapter.execute authority to run" if manifest else "adapter is not registered",
            )
        if "adapter.execute" not in _context_authority(context):
            raise PermissionError("adapter.execute authority is required for external execution")
        result = runtime.adapters.invoke(invocation, caller_authority=_context_authority(context), workspace=workspace)
        return SkillExecutionResult(self.name, result.status.value, {"adapter_result": result.to_dict()}, tuple(filter(None, (result.manifest_digest, result.executable_digest))), result.reason)


class CertificationHandler(SkillHandler):
    name = "elmos-certification-kernel"

    def execute(self, payload: Mapping[str, Any], context: Any, runtime: RuntimeDependencies) -> SkillExecutionResult:
        results = payload.get("proof_results")
        if not isinstance(results, list) or not results:
            return SkillExecutionResult(self.name, "BLOCKED", {"decision": "BLOCKED", "production_certification": "NOT_CERTIFIED"}, reason="proof results are absent")
        invalid = [
            item
            for item in results
            if not isinstance(item, Mapping)
            or item.get("status") != "PASS"
            or not _is_sha256(item.get("evidence_digest"))
        ]
        external_gate = payload.get("external_gate")
        if invalid:
            local_input_status = "INVALID"
            reason = "proof result claims are incomplete or not digest-shaped"
        else:
            local_input_status = "VALIDATED"
            reason = (
                "payload claims are syntax-valid but untrusted until the durable "
                "EvidenceService and CertificationService re-read and bind exact bytes"
            )
        # This public Skill handler receives caller payloads, not authoritative
        # EvidenceService records.  It must never manufacture readiness from
        # syntactically plausible proof claims.
        decision = "BLOCKED"
        digest = _digest({"proof_results": results, "external_gate": external_gate, "decision": decision})
        return SkillExecutionResult(
            self.name,
            decision,
            {
                "decision": decision,
                "local_input_status": local_input_status,
                "decision_digest": digest,
                "durable_evidence_verification": "NOT_RUN",
                "production_certification": "NOT_CERTIFIED",
            },
            (f"gate-input:sha256:{digest}",),
            reason,
            False,
        )


class _DomainHandler(SkillHandler):
    pack_name: str

    def execute(self, payload: Mapping[str, Any], context: Any, runtime: RuntimeDependencies) -> SkillExecutionResult:
        inputs = payload.get("inputs")
        if not isinstance(inputs, Mapping):
            raise ValueError("domain inputs must be an object")
        plan = runtime.domains.plan(self.pack_name, inputs)
        evidence = payload.get("evidence_by_obligation")
        if evidence is None:
            return SkillExecutionResult(self.name, "PLANNED", {"plan": plan.to_dict(), "external_evidence": "NOT_RUN"}, (plan.plan_id,))
        if not isinstance(evidence, Mapping):
            raise ValueError("evidence_by_obligation must be an object")
        decision = runtime.domains.evaluate(self.pack_name, evidence)  # type: ignore[arg-type]
        return SkillExecutionResult(self.name, decision.decision, {"plan": plan.to_dict(), "decision": decision.to_dict()}, (plan.plan_id,), certified=False)


class SpringLegacyModernizationHandler(_DomainHandler):
    name = "elmos-domain-spring-legacy-modernization"
    pack_name = "spring-legacy-modernization"


class CrossLanguageConversionHandler(_DomainHandler):
    name = "elmos-domain-cross-language-conversion"
    pack_name = "cross-language-conversion"


class MultiLanguageProjectGenerationHandler(_DomainHandler):
    name = "elmos-domain-multi-language-project-generation"
    pack_name = "multi-language-project-generation"


class SqlDialectRoutineConversionHandler(_DomainHandler):
    name = "elmos-domain-sql-dialect-routine-conversion"
    pack_name = "sql-dialect-routine-conversion"


class RepositoryRefactoringHandler(_DomainHandler):
    name = "elmos-domain-repository-refactoring"
    pack_name = "repository-refactoring"


class EvaluationTrustGateHandler(SkillHandler):
    name = "elmos-evaluation-trust-gate"

    def execute(self, payload: Mapping[str, Any], context: Any, runtime: RuntimeDependencies) -> SkillExecutionResult:
        records = payload.get("records")
        if not isinstance(records, list) or not records:
            raise ValueError("records must be a non-empty list")
        failures: list[str] = []
        seen_corpora: set[str] = set()
        for index, item in enumerate(records):
            if not isinstance(item, Mapping):
                failures.append(f"record {index} is not an object")
                continue
            corpus = item.get("corpus_digest")
            if not _is_sha256(corpus):
                failures.append(f"record {index} has no valid corpus digest")
            elif str(corpus) in seen_corpora:
                failures.append(f"record {index} reuses a corpus")
            else:
                seen_corpora.add(str(corpus))
            if item.get("executor") == item.get("verifier"):
                failures.append(f"record {index} has no role separation")
            if item.get("status") in {"UNKNOWN", "INCONCLUSIVE", "NOT_RUN", None}:
                failures.append(f"record {index} is non-passing")
        local_input_status = "VALIDATED" if not failures else "INVALID"
        # Caller records cannot establish independent execution or evidence
        # integrity.  Only the durable certification path may promote a
        # verified assessment to READY_FOR_EXTERNAL_GATE.
        decision = "BLOCKED"
        digest = _digest({"records": records, "failures": failures})
        return SkillExecutionResult(
            self.name,
            decision,
            {
                "decision": decision,
                "local_input_status": local_input_status,
                "failures": failures,
                "decision_digest": digest,
                "payload_independence_claims_trusted": False,
                "durable_evidence_verification": "NOT_RUN",
            },
            (f"trust-inputs:sha256:{digest}",),
            "; ".join(failures)
            or "local input validated; independent durable evidence is still required",
        )


class SelfImprovementGovernanceHandler(SkillHandler):
    name = "elmos-self-improvement-governance"

    def execute(self, payload: Mapping[str, Any], context: Any, runtime: RuntimeDependencies) -> SkillExecutionResult:
        observation = _required_string(payload, "observation")
        proposed_change = payload.get("proposed_change")
        if not isinstance(proposed_change, Mapping) or not proposed_change:
            raise ValueError("proposed_change must be a non-empty object")
        evidence_refs = _string_list(payload.get("evidence_refs", ()), "evidence_refs")
        proposal = {"observation": observation, "proposed_change": dict(proposed_change), "evidence_refs": evidence_refs, "requires_human_approval": True, "auto_apply": False}
        digest = _digest(proposal)
        return SkillExecutionResult(self.name, "READY_FOR_HUMAN_DECISION", {**proposal, "proposal_digest": digest}, tuple(evidence_refs), "self-improvement cannot self-approve or self-certify")


class CommercialOperationsFinOpsHandler(SkillHandler):
    name = "elmos-commercial-operations-finops"

    def execute(self, payload: Mapping[str, Any], context: Any, runtime: RuntimeDependencies) -> SkillExecutionResult:
        currency = _required_string(payload, "currency").upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        items = payload.get("line_items")
        if not isinstance(items, list) or not items:
            raise ValueError("line_items must be a non-empty list")
        normalized: list[dict[str, str]] = []
        total = Decimal("0")
        try:
            for item in items:
                if not isinstance(item, Mapping):
                    raise ValueError("line item must be an object")
                quantity = _bounded_decimal(
                    _required_string(item, "quantity"), "quantity"
                )
                unit_price = _bounded_decimal(
                    _required_string(item, "unit_price"), "unit_price"
                )
                if quantity < 0 or unit_price < 0:
                    raise ValueError("quantity and unit_price cannot be negative")
                amount = quantity * unit_price
                _validate_decimal_bounds(amount, "line item amount")
                total += amount
                _validate_decimal_bounds(total, "total")
                normalized.append({"name": _required_string(item, "name"), "quantity": format(quantity, "f"), "unit_price": format(unit_price, "f"), "amount": format(amount, "f")})
        except InvalidOperation as exc:
            raise ValueError("money and quantity values must be exact decimal strings") from exc
        output = {"currency": currency, "line_items": normalized, "total": format(total, "f"), "provider_bill_reconciliation": "NOT_RUN", "accounting_certification": "NOT_CERTIFIED"}
        digest = _digest(output)
        return SkillExecutionResult(self.name, "CALCULATED", {**output, "calculation_digest": digest}, (f"finops:sha256:{digest}",))


_HANDLER_CLASSES: tuple[Type[SkillHandler], ...] = (
    GoalSpecificationHandler,
    RepositoryIntelligenceHandler,
    RepositorySemanticCompilerHandler,
    AgenticReasoningHandler,
    TransformationHandler,
    ProofVerificationHandler,
    HarnessRuntimeHandler,
    CertificationHandler,
    SpringLegacyModernizationHandler,
    CrossLanguageConversionHandler,
    MultiLanguageProjectGenerationHandler,
    SqlDialectRoutineConversionHandler,
    RepositoryRefactoringHandler,
    EvaluationTrustGateHandler,
    SelfImprovementGovernanceHandler,
    CommercialOperationsFinOpsHandler,
)

# Exact repository-owned local cost model.  Units are internal integer
# microunits, not provider currency.  Provider/adapter cost remains unavailable
# until a digest-bound manifest and reconciled provider receipt exist.
_LOCAL_SKILL_BASE_COST_MICROUNITS: dict[str, int] = {
    handler.name: 1_000 + index * 100
    for index, handler in enumerate(_HANDLER_CLASSES, 1)
}


class SkillRuntime:
    def __init__(
        self,
        *,
        workspace_roots: Sequence[str | Path] = (),
        adapter_registry: AdapterRegistry | None = None,
        domain_orchestrator: DomainPackOrchestrator | None = None,
    ) -> None:
        roots = tuple(Path(root).resolve(strict=True) for root in workspace_roots)
        self.dependencies = RuntimeDependencies(roots, adapter_registry or AdapterRegistry(), domain_orchestrator or DomainPackOrchestrator(), SemanticCompiler(), ArchitectureExtractor())
        self.handlers: dict[str, SkillHandler] = {handler.name: handler for handler in (handler_class() for handler_class in _HANDLER_CLASSES)}
        if set(self.handlers) != set(SKILL_REGISTRY):
            raise RuntimeError("every v3 Skill must have one exact concrete handler")

    def execute(
        self,
        skill_name: str,
        payload: Mapping[str, Any],
        *,
        context: Any = None,
    ) -> SkillExecutionResult:
        if skill_name not in SKILL_REGISTRY:
            raise KeyError(f"unknown Skill: {skill_name}")
        if not isinstance(payload, Mapping):
            raise TypeError("Skill payload must be an object")
        return self.handlers[skill_name].execute(payload, context, self.dependencies)

    def estimate_cost_microunits(
        self,
        skill_name: str,
        *,
        input_bytes: int,
        max_output_bytes: int | None,
        wall_clock_milliseconds: int | None,
    ) -> int | None:
        """Return a conservative local upper bound, or ``None`` if unbounded."""

        if skill_name not in _LOCAL_SKILL_BASE_COST_MICROUNITS:
            raise KeyError(f"unknown Skill: {skill_name}")
        if max_output_bytes is None or wall_clock_milliseconds is None:
            return None
        if min(input_bytes, max_output_bytes, wall_clock_milliseconds) < 0:
            raise ValueError("cost dimensions cannot be negative")
        return (
            _LOCAL_SKILL_BASE_COST_MICROUNITS[skill_name]
            + input_bytes
            + max_output_bytes
            + wall_clock_milliseconds
        )

    def actual_cost_microunits(
        self,
        skill_name: str,
        *,
        input_bytes: int,
        output_bytes: int,
        wall_clock_milliseconds: int,
    ) -> int:
        """Meter bounded local work; external provider cost is never inferred."""

        if skill_name not in _LOCAL_SKILL_BASE_COST_MICROUNITS:
            raise KeyError(f"unknown Skill: {skill_name}")
        if min(input_bytes, output_bytes, wall_clock_milliseconds) < 0:
            raise ValueError("cost dimensions cannot be negative")
        return (
            _LOCAL_SKILL_BASE_COST_MICROUNITS[skill_name]
            + input_bytes
            + output_bytes
            + wall_clock_milliseconds
        )

    def describe(self) -> dict[str, Any]:
        return {
            "skills": [SKILL_REGISTRY[name].to_dict() for name in sorted(SKILL_REGISTRY)],
            "components": [COMPONENT_REGISTRY[name].to_dict() for name in sorted(COMPONENT_REGISTRY)],
            "domain_packs": [DOMAIN_PACKS[name].to_dict() for name in sorted(DOMAIN_PACKS)],
            "adapters": [
                DECLARED_ADAPTER_REGISTRY[name].to_dict()
                for name in sorted(DECLARED_ADAPTER_REGISTRY)
            ],
        }

    def readiness(self) -> tuple[bool, str]:
        if set(self.handlers) != set(SKILL_REGISTRY):
            return False, "Skill handler registry is incomplete"
        if len(COMPONENT_REGISTRY) != 96:
            return False, "component registry is incomplete"
        if len(DECLARED_ADAPTER_REGISTRY) != 27:
            return False, "declared adapter registry is incomplete"
        for root in self.dependencies.workspace_roots:
            try:
                if not root.is_dir() or root.is_symlink():
                    return False, f"workspace root is unavailable or unsafe: {root}"
            except OSError:
                return False, "workspace root readiness check failed"
        return True, "local runtime registries and configured workspace roots are ready"


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return list(value)


def _snapshot_limits(value: Any) -> SnapshotLimits:
    if value is None:
        return SnapshotLimits()
    if not isinstance(value, Mapping):
        raise ValueError("limits must be an object")
    allowed = {name for name in SnapshotLimits.__dataclass_fields__}
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"unknown snapshot limits: {sorted(unknown)}")
    return SnapshotLimits(**{str(key): int(item) for key, item in value.items()})


def _context_authority(context: Any) -> tuple[str, ...]:
    if context is None:
        return ()
    if isinstance(context, Mapping):
        value = context.get("authority", context.get("permissions", ()))
    else:
        value = getattr(context, "authority", getattr(context, "permissions", ()))
    return tuple(str(item) for item in value) if isinstance(value, (list, tuple, set)) else ()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _bounded_decimal(value: str, field_name: str) -> Decimal:
    parsed = Decimal(value)
    _validate_decimal_bounds(parsed, field_name)
    return parsed


def _validate_decimal_bounds(value: Decimal, field_name: str) -> None:
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    _sign, digits, exponent = value.as_tuple()
    scale = max(-exponent, 0)
    integer_digits = 0 if value.is_zero() else max(len(digits) + exponent, 0)
    # The persistence layer uses numeric(38,12), while the control-plane
    # accounting contract deliberately caps the integral part at 18 digits
    # to prevent unbounded quantities/costs from becoming an abuse vector.
    if scale > 12 or integer_digits > 18 or integer_digits + scale > 38:
        raise ValueError(
            f"{field_name} exceeds numeric(38,12) precision or scale"
        )


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "COMPONENT_REGISTRY",
    "SKILL_REGISTRY",
    "ComponentDescriptor",
    "SkillDescriptor",
    "SkillExecutionResult",
    "SkillRuntime",
]
