"""Skill 11 — layered verification and machine-adjudicated gates.

Verification runs bottom-up — parse, round-trip, scope containment, anti-cheat,
typecheck, build, changed-target tests, full tests, contract and schema checks —
and produces a decision per gate rather than a score.

Four rules decide what a "pass" means here, and each one exists because its
opposite is a real failure mode:

* **A blocking gate failure cannot be averaged away.**  There is no aggregate
  score that can outvote a hard gate.
* **Undecided is not passed.**  A gate whose evidence was never produced (no
  executor, no recording, a timeout) is ``fail`` when blocking.
* **Flaky is quarantined, not passed.**  A test that fails and then passes is
  reported as flaky and marked for investigation; it never counts as green.
* **Pre-existing failures are subtracted, not inherited.**  A failure present
  in the baseline is not attributed to this change — but only when the baseline
  is trustworthy; without one, every failure is a candidate regression.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .anticheat import AntiCheatReport
from .apicompat import ApiDiff, CompatibilityDecision
from .buildgraph import BaselineReport, BuildGraph, parse_failures
from .catalog import PACKAGE_VERSION
from .contracts import ContractError, GateOutcome, RiskClass, sha256_payload
from .executor import TransformResult
from .impact import TestSelection
from .policy import RefactorPolicy, evaluate_gate_set
from .sandbox import (
    ExecutionKind,
    ExecutionLedger,
    ExecutionRequest,
    ExecutionResult,
    SandboxExecutor,
)
from .sarif import SarifResult, SarifRule, SarifRun, build_log, count_by_level

#: Gates decided entirely from the patch and the index, with no executor.
STATIC_GATES = ("parse", "round-trip", "idempotence", "scope-containment", "anti-cheat", "evidence-completeness")

#: Gates that need a real toolchain and are therefore undecided without one.
EXECUTED_GATES = ("typecheck", "build", "changed-target-tests", "full-tests", "security-scan", "license-scan")

_TEST_ID = re.compile(r"([\w./\\-]+::[\w.\[\]-]+|[\w.]+#[\w]+|[\w./-]+\s+FAILED)")


@dataclass(frozen=True, slots=True)
class GateResult:
    gate: str
    outcome: GateOutcome
    blocking: bool
    detail: str = ""
    evidence_refs: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "decision": self.outcome.value,
            "blocking": self.blocking,
            "detail": self.detail,
            "evidenceRefs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class RegressionDiff:
    """New failures, fixed failures and the ones that were already broken."""

    new_failures: tuple[str, ...]
    fixed_failures: tuple[str, ...]
    pre_existing_failures: tuple[str, ...]
    flaky: tuple[str, ...] = ()
    baseline_trustworthy: bool = False

    @property
    def regressed(self) -> bool:
        return bool(self.new_failures)

    def to_payload(self) -> dict[str, Any]:
        return {
            "newFailures": list(self.new_failures),
            "fixedFailures": list(self.fixed_failures),
            "preExistingFailures": list(self.pre_existing_failures),
            "flaky": list(self.flaky),
            "baselineTrustworthy": self.baseline_trustworthy,
            "regressed": self.regressed,
        }


@dataclass(frozen=True, slots=True)
class EvidenceCoverage:
    changed_symbols: int
    covered_symbols: int
    changed_targets: int
    tested_targets: int
    uncovered_paths: tuple[str, ...]

    @property
    def symbol_coverage(self) -> Decimal:
        if self.changed_symbols == 0:
            return Decimal("1")
        return (Decimal(self.covered_symbols) / Decimal(self.changed_symbols)).quantize(Decimal("0.0001"))

    @property
    def target_coverage(self) -> Decimal:
        if self.changed_targets == 0:
            return Decimal("1")
        return (Decimal(self.tested_targets) / Decimal(self.changed_targets)).quantize(Decimal("0.0001"))

    def to_payload(self) -> dict[str, Any]:
        return {
            "changedSymbols": self.changed_symbols,
            "coveredSymbols": self.covered_symbols,
            "symbolCoverage": str(self.symbol_coverage),
            "changedTargets": self.changed_targets,
            "testedTargets": self.tested_targets,
            "targetCoverage": str(self.target_coverage),
            "uncoveredPaths": list(self.uncovered_paths),
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    gates: tuple[GateResult, ...]
    regressions: RegressionDiff
    coverage: EvidenceCoverage
    anti_cheat: AntiCheatReport
    ledger: ExecutionLedger = field(default_factory=ExecutionLedger)
    api_diff: ApiDiff | None = None
    compatibility: CompatibilityDecision | None = None
    sarif_runs: tuple[SarifRun, ...] = ()

    @property
    def blocking_failures(self) -> tuple[str, ...]:
        return tuple(
            item.gate for item in self.gates if item.blocking and item.outcome is GateOutcome.FAIL
        )

    @property
    def undecided(self) -> tuple[str, ...]:
        return tuple(
            item.gate
            for item in self.gates
            if item.outcome is GateOutcome.FAIL and "not produced" in item.detail
        )

    @property
    def passed(self) -> bool:
        return not self.blocking_failures

    def gate(self, name: str) -> GateResult | None:
        for item in self.gates:
            if item.gate == name:
                return item
        return None

    def sarif(self) -> dict[str, Any]:
        return build_log(self.sarif_runs)

    def to_payload(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "gateDecisions": [item.to_payload() for item in self.gates],
            "blockingFailures": list(self.blocking_failures),
            "undecidedBlockingGates": list(self.undecided),
            "regressionDiff": self.regressions.to_payload(),
            "evidenceCoverage": self.coverage.to_payload(),
            "antiCheat": self.anti_cheat.to_payload(),
            "sarifLevelCounts": count_by_level(self.sarif_runs),
            "executions": self.ledger.to_payload(),
            "apiDiff": None if self.api_diff is None else self.api_diff.to_payload(),
            "compatibilityDecision": None
            if self.compatibility is None
            else self.compatibility.to_payload(),
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


# ---------------------------------------------------------------------------
# Execution planning
# ---------------------------------------------------------------------------

_COMMANDS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "python": {
        "typecheck": ("mypy", "--strict"),
        "build": ("python", "-m", "compileall", "-q", "."),
        "changed-target-tests": ("pytest", "-q"),
        "full-tests": ("pytest", "-q"),
    },
    "typescript": {
        "typecheck": ("tsc", "--noEmit"),
        "build": ("npm", "run", "build"),
        "changed-target-tests": ("npm", "test", "--silent"),
        "full-tests": ("npm", "test", "--silent"),
    },
    "java": {
        "build": ("mvn", "-B", "-q", "compile"),
        "changed-target-tests": ("mvn", "-B", "-q", "test"),
        "full-tests": ("mvn", "-B", "-q", "verify"),
    },
    "go": {
        "typecheck": ("go", "vet", "./..."),
        "build": ("go", "build", "./..."),
        "changed-target-tests": ("go", "test", "./..."),
        "full-tests": ("go", "test", "./..."),
    },
    "csharp": {
        "build": ("dotnet", "build", "--nologo"),
        "changed-target-tests": ("dotnet", "test", "--nologo"),
        "full-tests": ("dotnet", "test", "--nologo"),
    },
}


def plan_executions(
    gates: Sequence[str],
    languages: Sequence[str],
    *,
    profile: str = "default",
) -> tuple[ExecutionRequest, ...]:
    """The commands that would decide the executed gates for these languages."""

    requests: list[ExecutionRequest] = []
    for gate in gates:
        if gate not in EXECUTED_GATES:
            continue
        for language in languages:
            argv = _COMMANDS.get(language, {}).get(gate)
            if argv is None:
                continue
            kind = {
                "typecheck": ExecutionKind.TYPECHECK,
                "build": ExecutionKind.BUILD,
                "changed-target-tests": ExecutionKind.TEST,
                "full-tests": ExecutionKind.TEST,
                "security-scan": ExecutionKind.SCAN,
                "license-scan": ExecutionKind.SCAN,
            }[gate]
            requests.append(
                ExecutionRequest(
                    request_id=f"{gate}:{language}",
                    kind=kind,
                    argv=argv,
                    timeout_seconds=3600 if gate.endswith("tests") else 1800,
                    description=f"{gate} for {language} ({profile})",
                )
            )
    return tuple(requests)


def _failures_of(result: ExecutionResult) -> tuple[str, ...]:
    identities: list[str] = []
    for stream in (result.stdout, result.stderr):
        identities.extend(match.group(1).strip() for match in _TEST_ID.finditer(stream))
    if not identities:
        identities = list(parse_failures(result))
    return tuple(dict.fromkeys(identities))


def compare_to_baseline(
    baseline: BaselineReport,
    results: Sequence[ExecutionResult],
    *,
    reruns: Sequence[ExecutionResult] = (),
) -> RegressionDiff:
    """Separate new failures from pre-existing ones, and detect flakiness.

    With an untrustworthy baseline every failure is reported as new: attributing
    a failure to "it was already broken" without evidence is how a real
    regression gets waved through.
    """

    current: set[str] = set()
    for result in results:
        if result.decisive and not result.succeeded:
            current.update(_failures_of(result))

    rerun_failures: set[str] = set()
    for result in reruns:
        if result.decisive and not result.succeeded:
            rerun_failures.update(_failures_of(result))
    flaky = tuple(sorted(current - rerun_failures)) if reruns else ()

    if not baseline.trustworthy:
        return RegressionDiff(
            new_failures=tuple(sorted(current)),
            fixed_failures=(),
            pre_existing_failures=(),
            flaky=flaky,
            baseline_trustworthy=False,
        )

    known = set(baseline.pre_existing_failures)
    return RegressionDiff(
        new_failures=tuple(sorted(current - known)),
        fixed_failures=tuple(sorted(known - current)),
        pre_existing_failures=tuple(sorted(current & known)),
        flaky=flaky,
        baseline_trustworthy=True,
    )


def compute_coverage(
    transform: TransformResult,
    tests: TestSelection,
    graph: BuildGraph,
) -> EvidenceCoverage:
    changed_symbols = set(transform.changed_symbols)
    covered = {
        symbol
        for symbol in changed_symbols
        if any(
            graph.target_to_tests.get(target)
            for path in transform.evidence.changed_paths
            for target in graph.targets_for(path)
        )
    }
    changed_targets = {
        target for path in transform.evidence.changed_paths for target in graph.targets_for(path)
    }
    tested = {target for target in changed_targets if graph.target_to_tests.get(target)}
    return EvidenceCoverage(
        changed_symbols=len(changed_symbols),
        covered_symbols=len(covered),
        changed_targets=len(changed_targets),
        tested_targets=len(tested),
        uncovered_paths=tests.uncovered_paths,
    )


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify(
    transform: TransformResult,
    *,
    policy: RefactorPolicy,
    baseline: BaselineReport,
    tests: TestSelection,
    graph: BuildGraph,
    anti_cheat: AntiCheatReport,
    executor: SandboxExecutor,
    languages: Sequence[str],
    risk_class: RiskClass,
    api_diff: ApiDiff | None = None,
    compatibility: CompatibilityDecision | None = None,
    impact_context: Mapping[str, Any] | None = None,
    reruns: Sequence[ExecutionResult] = (),
) -> ValidationReport:
    """Run every applicable gate and adjudicate the result."""

    context: dict[str, Any] = {
        "risk": {"class": risk_class.value},
        "execution": {"mutates": True},
        "impact": dict(impact_context or {}),
    }
    context["impact"].setdefault("public_api_touched", bool(api_diff and api_diff.changes))
    context["impact"].setdefault("database_touched", False)
    context["impact"].setdefault("security_touched", False)
    context["impact"].setdefault("performance_sensitive", False)

    applicable = [
        rule.gate
        for rule in policy.quality_gates
        if rule.applies(context) is not False
    ]

    raw: dict[str, bool | None] = {}
    details: dict[str, str] = {}

    # -- static gates ----------------------------------------------------
    raw["parse"] = not transform.evidence.round_trip_failures
    details["parse"] = (
        "; ".join(transform.evidence.round_trip_failures)
        if transform.evidence.round_trip_failures
        else "every changed file re-parses"
    )
    raw["round-trip"] = raw["parse"]
    details["round-trip"] = details["parse"]
    raw["idempotence"] = transform.evidence.idempotent
    details["idempotence"] = (
        "second run produced no change"
        if transform.evidence.idempotent
        else (
            "second run still changed: " + ", ".join(transform.evidence.second_run_paths)
            if transform.evidence.second_run_paths
            else "idempotence evidence was not produced"
        )
    )
    raw["scope-containment"] = not transform.evidence.scope_expansions
    details["scope-containment"] = (
        "; ".join(transform.evidence.scope_expansions)
        if transform.evidence.scope_expansions
        else "no file outside the declared scope was touched"
    )
    #: Rollback proof is computed, not asserted: invert the patch, apply it to
    #: the produced tree, and require the result to be the tree we started
    #: from.  A rollback that has never been exercised is not a rollback.
    if transform.patch.empty:
        raw["rollback-proof"] = None
        details["rollback-proof"] = "no patch was produced, so there is nothing to prove reversible"
    else:
        try:
            restored = transform.patch.invert().apply(transform.snapshot, verify_base=False)
        except ContractError as error:
            raw["rollback-proof"] = False
            details["rollback-proof"] = f"the inverse patch does not apply: {error.message}"
        else:
            raw["rollback-proof"] = restored.tree_digest == transform.evidence.base_tree_digest
            details["rollback-proof"] = (
                "the inverse patch restores the exact base tree digest"
                if raw["rollback-proof"]
                else f"inverting produced {restored.tree_digest}, not {transform.evidence.base_tree_digest}"
            )

    raw["anti-cheat"] = anti_cheat.clean
    details["anti-cheat"] = (
        "; ".join(f"{item.code} at {item.path}:{item.line}" for item in anti_cheat.blocking)
        if anti_cheat.blocking
        else "no suppression, skip or test removal detected"
    )

    # -- executed gates --------------------------------------------------
    requests = plan_executions([gate for gate in applicable if gate in EXECUTED_GATES], languages)
    ledger = ExecutionLedger()
    results: list[ExecutionResult] = []
    per_gate: dict[str, list[ExecutionResult]] = {}
    for request in requests:
        result = executor.execute(request)
        ledger = ledger.record(request, result)
        results.append(result)
        per_gate.setdefault(request.request_id.split(":", 1)[0], []).append(result)

    for gate in EXECUTED_GATES:
        if gate not in applicable:
            continue
        gate_results = per_gate.get(gate, [])
        decisive = [item for item in gate_results if item.decisive]
        if not gate_results:
            raw[gate] = None
            details[gate] = f"no command is known for '{gate}' in {', '.join(languages) or 'this repository'}"
        elif not decisive:
            raw[gate] = None
            details[gate] = (
                f"evidence was not produced ({gate_results[0].status.value}: "
                f"{gate_results[0].reason or 'no executor configured'})"
            )
        else:
            raw[gate] = all(item.succeeded for item in decisive)
            details[gate] = "; ".join(
                f"{item.request_id}: exit {item.exit_code}" for item in decisive
            )

    # -- contract gates --------------------------------------------------
    if api_diff is not None and compatibility is not None:
        raw["api-compatibility"] = compatibility.allowed
        details["api-compatibility"] = (
            "; ".join(f"{item.change} {item.identity}" for item in compatibility.violations[:10])
            if compatibility.violations
            else f"{len(api_diff.changes)} change(s), all permitted by policy '{compatibility.policy}'"
        )

    regressions = compare_to_baseline(baseline, results, reruns=reruns)
    if regressions.regressed:
        for gate in ("changed-target-tests", "full-tests"):
            if raw.get(gate):
                raw[gate] = False
                details[gate] = "new failures: " + ", ".join(regressions.new_failures[:10])
    if regressions.flaky:
        details["changed-target-tests"] = (
            details.get("changed-target-tests", "")
            + f" | {len(regressions.flaky)} flaky test(s) quarantined for investigation, not counted as passing"
        )

    coverage = compute_coverage(transform, tests, graph)
    raw["evidence-completeness"] = bool(transform.source_map()) and all(
        entry["actionIds"] for entry in transform.source_map()
    )
    details["evidence-completeness"] = (
        "every hunk maps to a recipe action"
        if raw["evidence-completeness"]
        else "one or more hunks have no owning recipe action"
    )

    outcomes, _ = evaluate_gate_set(policy, raw, context)

    def _blocking(name: str) -> bool:
        rule = policy.gate_rule(name)
        # A gate the policy does not mention is treated as blocking: an
        # unrecognised gate is not permission to ignore it.
        return True if rule is None else rule.blocking

    def _detail(name: str, outcome: GateOutcome) -> str:
        recorded = details.get(name)
        if recorded:
            return recorded
        if outcome is GateOutcome.FAIL and raw.get(name) is None:
            # An applicable gate with no result at all: say so explicitly
            # rather than emitting a failure with no explanation.
            return (
                f"gate '{name}' applies to this change but no evidence was produced for it; "
                "an undecided blocking gate fails"
            )
        return ""

    gates = tuple(
        GateResult(
            gate=name,
            outcome=outcome,
            blocking=_blocking(name),
            detail=_detail(name, outcome),
            evidence_refs=(transform.evidence.digest,),
        )
        for name, outcome in sorted(outcomes.items())
    )

    runs = [anti_cheat.sarif_run(PACKAGE_VERSION), _gate_run(gates, regressions, coverage)]
    return ValidationReport(
        gates=gates,
        regressions=regressions,
        coverage=coverage,
        anti_cheat=anti_cheat,
        ledger=ledger,
        api_diff=api_diff,
        compatibility=compatibility,
        sarif_runs=tuple(runs),
    )


def _gate_run(
    gates: Sequence[GateResult],
    regressions: RegressionDiff,
    coverage: EvidenceCoverage,
) -> SarifRun:
    results = [
        SarifResult(
            rule_id=f"gate/{item.gate}",
            level="error" if item.blocking else "warning",
            message=f"gate '{item.gate}' failed: {item.detail}",
            path=".",
            properties={"blocking": item.blocking},
        )
        for item in gates
        if item.outcome is GateOutcome.FAIL
    ]
    results.extend(
        SarifResult(
            rule_id="regression/new-failure",
            level="error",
            message=f"new test failure introduced by this change: {identity}",
            path=".",
        )
        for identity in regressions.new_failures[:200]
    )
    results.extend(
        SarifResult(
            rule_id="coverage/uncovered-change",
            level="warning",
            message=f"changed path has no linked test: {path}",
            path=path,
        )
        for path in coverage.uncovered_paths[:200]
    )
    rules = tuple(
        SarifRule(id=identity, name=identity.rsplit("/", 1)[-1], short_description=identity, default_level="error")
        for identity in sorted({item.rule_id for item in results})
    )
    return SarifRun(
        tool_name="elmos-verification",
        tool_version=PACKAGE_VERSION,
        rules=rules,
        results=tuple(results),
        invocation_successful=True,
    )


def junit_payload(report: ValidationReport) -> dict[str, Any]:
    """A JUnit-shaped summary for CI systems that consume it."""

    cases = [
        {
            "name": item.gate,
            "classname": "elmos.refactor.gates",
            "status": item.outcome.value,
            "failure": item.detail if item.outcome is GateOutcome.FAIL else None,
        }
        for item in report.gates
    ]
    return {
        "name": "elmos-repository-refactoring",
        "tests": len(cases),
        "failures": sum(1 for item in cases if item["status"] == "fail"),
        "skipped": sum(1 for item in cases if item["status"] == "not-applicable"),
        "testcases": cases,
    }


__all__ = [
    "EXECUTED_GATES",
    "STATIC_GATES",
    "EvidenceCoverage",
    "GateResult",
    "RegressionDiff",
    "ValidationReport",
    "compare_to_baseline",
    "compute_coverage",
    "junit_payload",
    "plan_executions",
    "verify",
]
