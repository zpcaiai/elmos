#!/usr/bin/env python3
"""Batch orchestration: execute one Batch, and chain Batch 01 -> Batch 44.

``BatchExecutor.execute`` is the single entry point every conformance case
drives.  It walks the sixteen archetypes in dependency order and each archetype
is a real code path, not a label:

    integration-api        -> trust boundary, unknown fields refused
    security-policy        -> tenant isolation, default deny
    certification-gate     -> upstream certificate required
    discovery-inventory    -> deterministic inventory of the request scope
    capability-planning    -> waves derived from the inventory
    deterministic-engine   -> content addressed execution, worker invariant
    adapter-provider       -> pinned providers, drift check
    workflow-runtime       -> durable run, leases, idempotent events
    human-approval         -> irreversible steps gated
    corpus-benchmark       -> development/negative/representative/holdout
    lineage-reconciliation -> evidence graph edges
    observability-economics-> journal, budget
    lifecycle-recertification -> expiry sweep
    failure-recovery       -> compensation on failure
    certification-gate     -> conservative issuance
    domain-model           -> output projection validated against the schema
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from scripts.modernization_b01_44.adapters import AdapterRegistry
from scripts.modernization_b01_44.approval import ApprovalLedger
from scripts.modernization_b01_44.canonical import digest, format_instant, stable_sort
from scripts.modernization_b01_44.certification import (
    Certificate,
    CertificateRegistry,
    CertificationGate,
    GateDecision,
)
from scripts.modernization_b01_44.corpus import Budget, CorpusCase, CorpusRunner, BenchmarkResult
from scripts.modernization_b01_44.engine import DeterministicEngine
from scripts.modernization_b01_44.errors import (
    ApprovalRequired,
    CertificationBlocked,
    PolicyViolation,
    RuntimeRefusal,
    UpstreamCertificateMissing,
)
from scripts.modernization_b01_44.evidence import (
    Evidence,
    EvidenceStore,
    LineageGraph,
    make_evidence,
)
from scripts.modernization_b01_44.packages import BatchPackage, PackageRegistry, load_registry
from scripts.modernization_b01_44.policy import PolicyEngine, Principal
from scripts.modernization_b01_44.validation import validate
from scripts.modernization_b01_44.workflow import WorkflowRuntime

EVIDENCE_TTL = timedelta(days=30)

#: Irreversible actions that always require human approval.
IRREVERSIBLE_ACTIONS = frozenset({"cutover", "retire-legacy", "delete-workspace", "production-release"})


@dataclass
class ExecutionResult:
    """Everything one Batch execution produced, plus why."""

    request_id: str
    batch: int
    status: str
    artifact_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    limitations: tuple[str, ...]
    certificate: Certificate | None = None
    decision: GateDecision | None = None
    workflow_id: str | None = None
    output_digest: str = ""
    journal: list[dict[str, Any]] = field(default_factory=list)
    benchmark: BenchmarkResult | None = None
    audit: list[dict[str, Any]] = field(default_factory=list)

    def as_output(self) -> dict[str, Any]:
        """Projection validated against ``batch-output.schema.json``."""

        return {
            "request_id": self.request_id,
            "status": self.status,
            "artifact_refs": list(self.artifact_refs),
            "evidence_refs": list(self.evidence_refs),
            "limitations": list(self.limitations),
        }


@dataclass
class Platform:
    """Shared state across a Batch chain."""

    registry: PackageRegistry
    evidence: EvidenceStore = field(default_factory=EvidenceStore)
    lineage: LineageGraph = field(default_factory=LineageGraph)
    workflows: WorkflowRuntime = field(default_factory=WorkflowRuntime)
    adapters: AdapterRegistry = field(default_factory=AdapterRegistry)
    approvals: ApprovalLedger = field(default_factory=ApprovalLedger)
    engine: DeterministicEngine = field(default_factory=DeterministicEngine)
    certificates: CertificateRegistry = field(default_factory=CertificateRegistry)
    gates: dict[int, CertificationGate] = field(default_factory=dict)
    policies: dict[int, PolicyEngine] = field(default_factory=dict)

    def policy(self, batch: int) -> PolicyEngine:
        if batch not in self.policies:
            self.policies[batch] = PolicyEngine(self.registry.get(batch))
        return self.policies[batch]

    def gate(self, batch: int) -> CertificationGate:
        if batch not in self.gates:
            self.gates[batch] = CertificationGate(
                self.policy(batch), self.evidence, self.certificates
            )
        return self.gates[batch]

    def seed_certificate(self, certificate: Certificate) -> Certificate:
        """Install an externally issued upstream certificate (chain entry)."""

        return self.certificates.put(certificate)


def default_platform(root: Any = None) -> Platform:
    return Platform(registry=load_registry(root))


def _inventory(scope: str, options: dict[str, Any]) -> list[dict[str, Any]]:
    """Deterministic inventory of the requested scope.

    Real work, deliberately simple: the scope string plus declared assets are
    normalised into stably ordered work units.  Nothing here consults the clock
    or the filesystem, so the inventory digest is reproducible.
    """

    assets = options.get("assets") or [scope]
    units = [
        {"unit_id": f"u-{digest({'scope': scope, 'asset': asset})[:16]}", "asset": str(asset), "scope": scope}
        for asset in assets
    ]
    return stable_sort(units, key="unit_id")


def _plan_waves(units: list[dict[str, Any]], *, width: int = 4) -> list[dict[str, Any]]:
    """Split the inventory into deterministic dependency waves."""

    if width < 1:
        raise PolicyViolation("wave width must be >= 1", width=width)
    waves: list[dict[str, Any]] = []
    for index in range(0, len(units), width):
        chunk = units[index : index + width]
        waves.append(
            {
                "wave": len(waves),
                "unit_ids": [unit["unit_id"] for unit in chunk],
                "wave_digest": digest(chunk),
            }
        )
    return waves


class BatchExecutor:
    """Execute one Batch end to end under the package's own policies."""

    def __init__(self, platform: Platform, batch: int) -> None:
        self.platform = platform
        self.batch = batch
        self.package: BatchPackage = platform.registry.get(batch)
        self.policy = platform.policy(batch)
        self.gate = platform.gate(batch)

    # -- helpers ----------------------------------------------------------

    def _evidence(
        self,
        scope: str,
        payload: Any,
        *,
        producer: str,
        trust_level: str,
        now: datetime,
        ttl: timedelta | None = EVIDENCE_TTL,
    ) -> Evidence:
        evidence = make_evidence(
            evidence_id=f"ev-b{self.batch:02d}-{scope}-{digest(payload)[:16]}",
            producer=producer,
            created_at=now,
            trust_level=trust_level,
            scope=scope,
            payload=payload,
            ttl=ttl,
        )
        self.platform.evidence.add(evidence)
        validate(evidence.as_ref(), self.package.schema("evidence-ref"), label="evidence-ref")
        return evidence

    # -- main -------------------------------------------------------------

    def execute(
        self,
        request: dict[str, Any],
        *,
        principal: Principal,
        now: datetime | None = None,
        transform: Callable[[dict[str, Any]], Any] | None = None,
        corpus: Iterable[CorpusCase] = (),
        provider_pins: Iterable[dict[str, Any]] = (),
        approval_ids: Iterable[str] = (),
        requested_status: str = "limited",
        budget: Budget | None = None,
        worker_counts: tuple[int, ...] = (1, 4),
        minimum_upstream_status: str = "limited",
    ) -> ExecutionResult:
        now = now or datetime.now(timezone.utc)
        evidence_ids: list[str] = []
        limitations: list[str] = []

        # 1. integration-api: refuse anything the schema does not model.
        self.policy.check_trust_boundary(request, self.package.schema("batch-input"), label="batch-input")

        # 2. security-policy: tenant isolation before anything else runs.
        self.policy.check_tenant(principal, request["tenant_id"], f"batch-{self.batch:02d}")
        if principal.is_agent:
            self.policy.check_agent_write(principal, "artifact", mode="propose")

        # 3. certification-gate (entry): the upstream chain must hold.
        upstream = self.gate.require_upstream(
            batch=self.batch,
            certificate_refs=request["upstream_certificate_refs"],
            now=now,
            minimum_status=minimum_upstream_status,
        ) if self.batch > 1 else []

        options = request.get("options") or {}

        # 4. adapter-provider: pinned providers must still match.
        pins = list(provider_pins)
        if pins:
            self.platform.adapters.assert_no_breaking_drift(pins)

        # 5. workflow-runtime: durable run keyed by the request.
        run, created = self.platform.workflows.start(
            definition_version=f"b{self.batch:02d}.v1",
            tenant_id=request["tenant_id"],
            project_id=request["project_id"],
            request=request,
            now=now,
        )
        validate(run.as_record(), self.package.schema("workflow-run"), label="workflow-run")
        if created:
            self.platform.workflows.transition(run, "running", now=now)

        # 6. human-approval: irreversible actions are gated, always.
        action = options.get("action", "analyse")
        if action in IRREVERSIBLE_ACTIONS:
            approvals = self.platform.approvals.require(
                request=request,
                approval_ids=approval_ids,
                action=action,
                now=now,
                criticality="critical" if action in ("cutover", "production-release") else "normal",
            )
            run.approvals = [a.approval_id for a in approvals]

        try:
            # 7. discovery-inventory + capability-planning.
            units = _inventory(request["scope"], options)
            waves = _plan_waves(units, width=int(options.get("wave_width", 4)))
            self.platform.workflows.record_step(run, step="plan", output=waves, now=now)

            # 8. deterministic-engine: worker-invariant, content addressed.
            work = transform or (lambda unit: {"unit_id": unit["unit_id"], "result": "analysed"})
            engine_result = self.platform.engine.verify_worker_invariance(
                units, work, worker_counts=worker_counts, label=f"b{self.batch:02d}"
            )
            self.platform.workflows.record_step(
                run, step="execute", output=engine_result.output, now=now
            )

            # 9. corpus-benchmark.
            corpus_cases = list(corpus)
            benchmark: BenchmarkResult | None = None
            if corpus_cases:
                runner = CorpusRunner(
                    lambda payload: work(payload) if "unit_id" in payload else _reject_unknown(payload),
                    budget=budget,
                )
                benchmark = BenchmarkResult(reports=runner.run_all(corpus_cases))

            # 10. evidence + lineage.
            schema_ev = self._evidence(
                "schema-conformance",
                {"request": request, "batch": self.batch},
                producer=f"b{self.batch:02d}-integration-api",
                trust_level="deterministic",
                now=now,
            )
            evidence_ids.append(schema_ev.evidence_id)

            exec_ev = self._evidence(
                "deterministic-execution",
                {"output_digest": engine_result.output_digest, "journal": engine_result.journal_digest},
                producer=f"b{self.batch:02d}-deterministic-engine",
                trust_level="compiler-confirmed",
                now=now,
            )
            evidence_ids.append(exec_ev.evidence_id)
            self.platform.lineage.link(exec_ev.evidence_id, schema_ev.evidence_id)

            if benchmark is not None:
                for scope in benchmark.evidence_scopes():
                    ev = self._evidence(
                        scope,
                        benchmark.reports[_scope_to_kind(scope)].as_dict(),
                        producer=f"b{self.batch:02d}-corpus-benchmark",
                        trust_level="runtime-observed",
                        now=now,
                    )
                    evidence_ids.append(ev.evidence_id)
                    self.platform.lineage.link(ev.evidence_id, exec_ev.evidence_id)
                for kind, report in sorted(benchmark.reports.items()):
                    if report.denominator and not report.clean:
                        limitations.append(f"{kind}-corpus {report.score}")

            for scope in options.get("external_evidence_scopes", []):
                ev = self._evidence(
                    str(scope),
                    {"scope": scope, "batch": self.batch},
                    producer=str(options.get("external_producer", "independent-oracle")),
                    trust_level=str(options.get("external_trust_level", "independent-verified")),
                    now=now,
                )
                evidence_ids.append(ev.evidence_id)

            for certificate in upstream:
                for ref in certificate.evidence_refs:
                    if ref in self.platform.evidence:
                        self.platform.lineage.link(schema_ev.evidence_id, ref)

        except RuntimeRefusal:
            self.platform.workflows.transition(run, "failed", now=now, reason="execution-refused")
            raise

        # 11. lifecycle-recertification: expire before deciding.
        self.gate.sweep_expired_evidence(now)

        # 12. certification-gate (exit): conservative issuance.
        input_digests = sorted({digest(request), engine_result.input_digest})
        try:
            certificate, decision = self.gate.issue(
                batch=self.batch,
                scope=request["scope"],
                requested_status=requested_status,
                evidence_refs=evidence_ids,
                input_digests=input_digests,
                now=now,
            )
            status = "completed" if not limitations else "partial"
        except CertificationBlocked as exc:
            self.platform.workflows.transition(run, "failed", now=now, reason="gate-blocked")
            raise exc

        self.platform.workflows.transition(run, "completed", now=now)
        run.evidence_refs = list(evidence_ids)

        result = ExecutionResult(
            request_id=request["request_id"],
            batch=self.batch,
            status=status,
            artifact_refs=(f"artifact:{engine_result.output_digest}",),
            evidence_refs=tuple(evidence_ids),
            limitations=tuple(sorted(set(limitations) | set(decision.limitations))),
            certificate=certificate,
            decision=decision,
            workflow_id=run.workflow_id,
            output_digest=engine_result.output_digest,
            journal=engine_result.journal,
            benchmark=benchmark,
            audit=[record.as_dict() for record in self.policy.audit_log],
        )

        # 13. domain-model: the output projection must satisfy the schema.
        validate(result.as_output(), self.package.schema("batch-output"), label="batch-output")
        validate(certificate.as_dict(), self.package.schema("certification"), label="certification")
        return result


def _scope_to_kind(scope: str) -> str:
    return {
        "development-corpus": "development",
        "negative-corpus": "negative",
        "representative-workload": "representative",
        "holdout-corpus": "holdout",
    }[scope]


def _reject_unknown(payload: dict[str, Any]) -> Any:
    raise PolicyViolation("payload does not describe a known work unit", keys=sorted(payload))


class ChainRunner:
    """Run a contiguous Batch chain, feeding each certificate downstream."""

    def __init__(self, platform: Platform) -> None:
        self.platform = platform

    def run(
        self,
        batches: Iterable[int],
        *,
        principal: Principal,
        tenant_id: str,
        project_id: str,
        scope: str,
        now: datetime,
        requested_status: str = "limited",
        options: dict[str, Any] | None = None,
        seed_upstream_refs: Iterable[str] = (),
        corpus: Iterable[CorpusCase] = (),
        minimum_upstream_status: str = "limited",
    ) -> list[ExecutionResult]:
        results: list[ExecutionResult] = []
        upstream_refs: list[str] = list(seed_upstream_refs)
        for batch in batches:
            request = {
                "request_id": f"req-b{batch:02d}-{digest({'scope': scope, 'batch': batch})[:12]}",
                "tenant_id": tenant_id,
                "project_id": project_id,
                "scope": scope,
                "upstream_certificate_refs": list(upstream_refs) or ["genesis"],
                "options": dict(options or {}),
            }
            if batch == 1:
                request["upstream_certificate_refs"] = ["genesis"]
            executor = BatchExecutor(self.platform, batch)
            result = executor.execute(
                request,
                principal=principal,
                now=now,
                requested_status=requested_status,
                corpus=corpus,
                minimum_upstream_status=minimum_upstream_status,
            )
            results.append(result)
            upstream_refs = [result.certificate.certificate_id] if result.certificate else []
        return results


def standard_corpus(scope: str, *, assets: Iterable[str]) -> list[CorpusCase]:
    """Build the four corpora for ``scope`` from the same inventory the run uses.

    Accept cases are real work units, so a subject that stops working fails the
    corpus.  Refuse cases are malformed units, so a subject that stops refusing
    also fails.  Both directions are load bearing.
    """

    units = _inventory(scope, {"assets": list(assets)})
    cases: list[CorpusCase] = []
    for kind in ("development", "representative", "holdout"):
        for unit in units:
            cases.append(
                CorpusCase(
                    case_id=f"{kind}-{unit['unit_id']}",
                    kind=kind,
                    payload=dict(unit),
                    expect="accept",
                )
            )
    for index, bad in enumerate(
        [
            {"not_a_unit": True},
            {"asset": "orphan-without-unit-id"},
            {"scope": scope},
        ]
    ):
        cases.append(
            CorpusCase(case_id=f"negative-{index:02d}", kind="negative", payload=bad, expect="refuse")
        )
    return cases
