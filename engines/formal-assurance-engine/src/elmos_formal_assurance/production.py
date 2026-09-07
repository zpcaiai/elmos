from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Protocol

from .artifact_store import ArtifactStore
from .canonical import digest_value
from .contracts import AssuranceLevel, ProofStatus, Scope, SkillOutcome, TrustedIdentity, utc_now
from .database import SQLiteDifferentialExecutor
from .execution import (
    ExecutionAuthorizationError,
    ExecutionContractError,
    ExecutionPermitSigner,
    NativeExecutionReceipt,
    NativeExecutionRequest,
    NativeVerificationExecutor,
    ResourceLimits,
    ToolchainRegistration,
)
from .observability import FormalObservabilityService
from .store import StateStore


class ProductionContext(Protocol):
    skill_id: str
    handler_id: str
    scope: Scope
    subject_id: str
    identity: TrustedIdentity
    payload: dict[str, Any]


class ProductionSkillExecutor:
    """Explicit production adapters for every formerly partial Skill.

    Each public method is intentionally named and called by one exact Skill
    handler. Domain primitives are shared, but no unknown Skill can fall through
    a generic production dispatcher.
    """

    def __init__(
        self,
        *,
        store: StateStore,
        artifact_store: ArtifactStore | None,
        permit_signer: ExecutionPermitSigner | None,
        toolchains: tuple[ToolchainRegistration, ...],
        limits: ResourceLimits,
        execution_root: Any = None,
        observability: FormalObservabilityService | None = None,
    ) -> None:
        self.store = store
        self.artifact_store = artifact_store
        self.permit_signer = permit_signer
        self.limits = limits
        self.native = NativeVerificationExecutor(
            store=store,
            artifact_store=artifact_store,
            permit_signer=permit_signer,
            toolchains=toolchains,
            limits=limits,
            execution_root=execution_root,
        )
        self.database = SQLiteDifferentialExecutor(
            store=store,
            artifact_store=artifact_store,
            permit_signer=permit_signer,
            limits=limits,
        )
        self.observability = observability or FormalObservabilityService(store)

    @staticmethod
    def _code_complete(local: SkillOutcome) -> SkillOutcome:
        if local.implementation_state == "PRODUCTION_CODE_COMPLETE":
            return local
        return replace(local, implementation_state="PRODUCTION_CODE_COMPLETE")

    def _native(
        self,
        ctx: ProductionContext,
        local: SkillOutcome,
        allowed: tuple[str, ...],
    ) -> SkillOutcome:
        local = self._code_complete(local)
        if local.proof_status == ProofStatus.REFUTED_WITH_COUNTEREXAMPLE:
            if "productionExecution" in ctx.payload:
                output = dict(local.output)
                output["productionExecution"] = {
                    "state": "SKIPPED_LOCAL_COUNTEREXAMPLE",
                    "permitConsumed": False,
                }
                return replace(local, output=output)
            return local
        receipt = self.native.execute(
            scope=ctx.scope,
            identity=ctx.identity,
            skill_id=ctx.skill_id,
            subject_id=ctx.subject_id,
            payload=ctx.payload,
            allowed_adapters=allowed,
        )
        if receipt is None:
            return local
        return self._merge(local, receipt)

    def _database(
        self,
        ctx: ProductionContext,
        local: SkillOutcome,
        allowed_native: tuple[str, ...],
    ) -> SkillOutcome:
        local = self._code_complete(local)
        if local.proof_status == ProofStatus.REFUTED_WITH_COUNTEREXAMPLE:
            return self._native(ctx, local, allowed_native)
        receipt = self.database.execute(
            scope=ctx.scope,
            identity=ctx.identity,
            skill_id=ctx.skill_id,
            subject_id=ctx.subject_id,
            payload=ctx.payload,
        )
        if receipt is not None:
            return self._merge(local, receipt)
        return self._native(ctx, local, allowed_native)

    @staticmethod
    def _merge(local: SkillOutcome, receipt: NativeExecutionReceipt) -> SkillOutcome:
        output = dict(local.output)
        output["productionExecution"] = receipt.to_dict()
        if receipt.counterexample is not None:
            output["counterexample"] = receipt.counterexample
            output["counterexampleId"] = "cex-" + digest_value(
                receipt.counterexample
            ).removeprefix("sha256:")[:32]
            output["replayable"] = True
        output["bounded"] = receipt.assurance_level in {
            AssuranceLevel.A0_TESTED,
            AssuranceLevel.A1_BOUNDED,
        }
        capability = (
            "CODE_COMPLETE_NATIVE_EXECUTED_SELF_ATTESTED"
            if receipt.proof_status
            not in {
                ProofStatus.UNKNOWN_TIMEOUT,
                ProofStatus.UNKNOWN_RESOURCE_LIMIT,
                ProofStatus.UNSUPPORTED,
                ProofStatus.ASSUMPTION_REQUIRED,
            }
            else "CODE_COMPLETE_RUNTIME_EVIDENCE_BLOCKED"
        )
        return SkillOutcome(
            skill_id=local.skill_id,
            handler_id=local.handler_id,
            implementation_state="PRODUCTION_CODE_COMPLETE",
            capability_state=capability,
            proof_status=receipt.proof_status,
            assurance_level=receipt.assurance_level,
            mode=(
                "DATABASE_DIFFERENTIAL"
                if receipt.adapter_id == "sqlite-differential"
                else "NATIVE_TOOLCHAIN"
            ),
            output=output,
            diagnostics=tuple(local.diagnostics) + tuple(receipt.diagnostics) + (
                "native execution receipt is local self-attested engineering evidence",
            ),
            artifact_refs=tuple(local.artifact_refs) + tuple(receipt.artifact_refs),
            external_evidence_status="NOT_RUN",
            certification_status="NOT_CERTIFIED",
        )

    # Project and API verification.
    def api_contract(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("alloy", "boogie", "cvc5", "z3"))

    def architecture_constraint(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("alloy", "boogie", "cvc5", "z3"))

    def data_invariant(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("alloy", "boogie", "cvc5", "dafny", "z3"))

    def generated_workflow(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("alloy", "apalache", "cvc5", "tlc", "z3"))

    def requirement_spec(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("alloy", "boogie", "cvc5", "z3"))

    def resource_termination(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("dafny", "frama-c", "key", "lean", "openjml"))

    def liveness_fairness(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("apalache", "tlc"))

    def tenant_noninterference(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("alloy", "boogie", "cvc5", "z3"))

    def verified_core(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("dafny", "frama-c", "kani", "key", "lean", "openjml"))

    # Cross-language refinement.
    def concurrency_async(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("alloy", "apalache", "jpf", "tlc"))

    def cross_language_product(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("alive2", "boogie", "cvc5", "dafny", "k-framework", "z3"))

    def effect_exception(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("alive2", "boogie", "cvc5", "k-framework", "z3"))

    def language_profile(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("dafny", "k-framework", "lean"))

    def legacy_trace(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("alive2", "cvc5", "k-framework", "z3"))

    def proof_carrying(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("dafny", "key", "lean", "openjml"))

    def repository_composer(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("boogie", "cvc5", "dafny", "z3"))

    def rule_preservation(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("boogie", "cvc5", "dafny", "z3"))

    def semantic_gap(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("alloy", "boogie", "cvc5", "z3"))

    def semantic_ir(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("dafny", "k-framework", "lean"))

    # SQL and database verification.
    def ddl_constraint(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._database(ctx, local, ("alloy", "cvc5", "sqlsolver", "z3"))

    def dml_state(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._database(ctx, local, ("cvc5", "sqlsolver", "verieql", "z3"))

    def dynamic_sql(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._database(ctx, local, ("cvc5", "sqlsolver", "z3"))

    def query_equivalence(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._database(ctx, local, ("cvc5", "sqlsolver", "verieql", "z3"))

    def routine_contract(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._database(ctx, local, ("boogie", "cvc5", "dafny", "z3"))

    def schema_losslessness(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._database(ctx, local, ("alloy", "cvc5", "sqlsolver", "z3"))

    def sql_semantic_ir(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._database(ctx, local, ("cvc5", "sqlsolver", "verieql", "z3"))

    def sql_transaction(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._database(ctx, local, ("boogie", "cvc5", "sqlsolver", "z3"))

    def sql_type_precision(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._database(ctx, local, ("cvc5", "sqlsolver", "z3"))

    def trigger_trace(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._database(ctx, local, ("apalache", "cvc5", "tlc", "z3"))

    # Spring/JVM verification. Maven/Gradle adapters execute an offline verify
    # lifecycle only inside the strong OCI sandbox.
    def java_jml(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("key", "openjml"))

    def spring_data(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("key", "maven-spring", "gradle-spring", "openjml"))

    def spring_exception(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("jpf", "key", "maven-spring", "gradle-spring", "openjml"))

    def spring_order(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("jpf", "maven-spring", "gradle-spring"))

    def spring_proxy(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("jpf", "key", "maven-spring", "gradle-spring"))

    def spring_route(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("jpf", "maven-spring", "gradle-spring", "openjml"))

    def spring_security(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("jpf", "key", "maven-spring", "gradle-spring", "openjml"))

    def spring_session(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("jpf", "maven-spring", "gradle-spring"))

    def spring_transaction(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("jpf", "key", "maven-spring", "gradle-spring", "openjml"))

    # Runtime boundary and observability verification.
    def reflection_ffi(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        return self._native(ctx, local, ("javap", "nm", "otool", "readelf"))

    def formal_observability(self, ctx: ProductionContext, local: SkillOutcome) -> SkillOutcome:
        local = self._code_complete(local)
        objectives = ctx.payload.get("objectives", {})
        if not isinstance(objectives, dict):
            raise ExecutionContractError("objectives must be an object")
        snapshot = self.observability.snapshot(ctx.scope, objectives=objectives)
        output = dict(local.output)
        output["runtimeSnapshot"] = snapshot
        output["opentelemetryExport"] = "NOT_RUN"
        raw = ctx.payload.get("productionExecution")
        if raw is None:
            return replace(
                local,
                output=output,
                capability_state="CODE_COMPLETE_EXTERNAL_EVIDENCE_REQUIRED",
            )
        request = NativeExecutionRequest.from_payload(
            raw,
            scope=ctx.scope,
            skill_id=ctx.skill_id,
            subject_id=ctx.subject_id,
            limits=self.limits,
        )
        if request.adapter_id != "otlp-http" or request.query_semantics != "BOUNDARY_INVENTORY":
            raise ExecutionAuthorizationError("formal observability permits only otlp-http export")
        files = {item.path: item.data for item in request.files}
        if set(files) != {"export-policy.json"}:
            raise ExecutionContractError("otlp-http requires one export-policy.json file")
        try:
            policy = json.loads(files["export-policy.json"])
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExecutionContractError("export-policy.json is invalid") from exc
        if policy != {
            "format": "elmos-formal-telemetry-export-policy/v1",
            "snapshotDigest": digest_value(snapshot),
        }:
            raise ExecutionAuthorizationError("telemetry export policy is not bound to the exact snapshot")
        if self.permit_signer is None:
            raise ExecutionAuthorizationError("telemetry execution permit authority is not configured")
        self.permit_signer.verify(
            request.permit,
            scope=ctx.scope,
            identity=ctx.identity,
            skill_id=ctx.skill_id,
            subject_id=ctx.subject_id,
            adapter_id=request.adapter_id,
            execution_digest=request.binding_digest,
        )
        self.store.consume_execution_permit(
            ctx.scope,
            request.permit.permit_id,
            request.permit.nonce,
            request.binding_digest,
            request.permit.expires_at_epoch,
        )
        export_result = self.observability.export(snapshot)
        execution_id = "exec-" + request.binding_digest.removeprefix("sha256:")[:32]
        receipt = {
            "format": "elmos-formal-telemetry-export-receipt/v1",
            "executionId": execution_id,
            "bindingDigest": request.binding_digest,
            "snapshotDigest": digest_value(snapshot),
            "export": export_result,
            "createdAt": utc_now(),
            "externalEvidenceStatus": "LOCAL_EXECUTED_SELF_ATTESTED",
            "certificationStatus": "NOT_CERTIFIED",
        }
        self.store.put_execution_receipt(
            ctx.scope, execution_id, request.binding_digest, receipt
        )
        output["opentelemetryExport"] = receipt
        return SkillOutcome(
            skill_id=local.skill_id,
            handler_id=local.handler_id,
            implementation_state="PRODUCTION_CODE_COMPLETE",
            capability_state="CODE_COMPLETE_EXTERNAL_EXPORT_EXECUTED_SELF_ATTESTED",
            proof_status=ProofStatus.RUNTIME_MONITORED,
            assurance_level=AssuranceLevel.A0_TESTED,
            mode="RUNTIME_MONITORING",
            output=output,
            diagnostics=tuple(local.diagnostics) + (
                "telemetry delivery is not independent assurance or certification evidence",
            ),
            artifact_refs=local.artifact_refs,
            external_evidence_status="NOT_RUN",
            certification_status="NOT_CERTIFIED",
        )


__all__ = ["ProductionContext", "ProductionSkillExecutor"]
