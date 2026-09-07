from __future__ import annotations

from typing import Any

from .artifact_store import ArtifactStore
from .canonical import canonical_json, digest_value, validate_digest, validate_identifier
from .contracts import AssuranceLevel, ProofResult, ProofRunState, ProofStatus, Scope
from .store import StateStore, StoreError


class LocalEvaluationError(ValueError):
    """Raised when a local bounded evaluator request is malformed or unsafe."""


class LocalBoundedExecutor:
    """Execute only repository-owned, data-only bounded proof evaluators.

    This executor never loads package code, expressions, plugins, commands, or
    solver scripts.  It evaluates finite typed observations and therefore may
    emit A1 bounded evidence or a replayable counterexample, never a proof.
    """

    _KINDS = {"EXACT_EQUALITY", "PREDICATE_SAMPLES", "TRACE_EQUIVALENCE"}

    def __init__(
        self,
        store: StateStore,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        self.store = store
        self.artifact_store = artifact_store

    def execute(
        self,
        scope: Scope,
        run_id: str,
        worker_id: str,
        token: int,
        evaluation: dict[str, Any],
        *,
        assumption_hash: str,
        tcb_hash: str,
    ) -> dict[str, Any]:
        validate_identifier(run_id, "runId")
        validate_identifier(worker_id, "workerId")
        validate_digest(assumption_hash, "assumptionHash")
        validate_digest(tcb_hash, "tcbHash")
        if not isinstance(token, int) or isinstance(token, bool) or token < 1:
            raise LocalEvaluationError("token must be a positive integer")
        if not isinstance(evaluation, dict):
            raise LocalEvaluationError("evaluation must be an object")
        if len(canonical_json(evaluation)) > 4 * 1024 * 1024:
            raise LocalEvaluationError("evaluation exceeds the local execution bound")

        run = self.store.get_run(scope, run_id)
        if run["state"] != ProofRunState.RUNNING.value:
            raise StoreError("local execution requires a running proof run")
        if run["owner_id"] != worker_id or int(run["fencing_token"]) != token:
            raise StoreError("local execution rejected a stale or non-owner worker")
        if run["mode"] != "BOUNDED":
            raise LocalEvaluationError(
                "the local data-only executor is authorized only for BOUNDED runs"
            )
        if run["engine"] not in {"local", "elmos-local-bounded"}:
            raise LocalEvaluationError("proof run selected a non-local engine")

        kind = str(evaluation.get("kind", ""))
        if kind not in self._KINDS:
            raise LocalEvaluationError(
                "evaluation kind must be EXACT_EQUALITY, PREDICATE_SAMPLES, or TRACE_EQUIVALENCE"
            )
        status, counterexample, bound, diagnostics = self._evaluate(kind, evaluation)
        counterexample_id = None
        if counterexample is not None:
            counterexample_id = "cex-" + digest_value(
                {
                    "runId": run_id,
                    "obligationId": run["obligation_id"],
                    "counterexample": counterexample,
                }
            ).removeprefix("sha256:")[:32]

        evidence = {
            "format": "elmos-local-bounded-evidence/v1",
            "runId": run_id,
            "obligationId": run["obligation_id"],
            "engine": run["engine"],
            "engineVersion": run["engine_version"],
            "formulaHash": run["formula_hash"],
            "evaluationKind": kind,
            "evaluationDigest": digest_value(evaluation),
            "bound": bound,
            "status": status.value,
            "counterexampleId": counterexample_id,
            "counterexample": counterexample,
            "assumptionHash": assumption_hash,
            "tcbHash": tcb_hash,
            "scopeDigest": digest_value(scope.to_dict()),
        }
        artifacts: tuple[dict[str, Any], ...] = ()
        if self.artifact_store is not None:
            artifact = self.artifact_store.put(
                scope.tenant_id,
                canonical_json(evidence) + b"\n",
                media_type="application/vnd.elmos.local-proof-evidence+json",
                retention_class="AUDIT",
            )
            artifacts = (artifact,)

        result = ProofResult(
            run_id=run_id,
            obligation_id=run["obligation_id"],
            status=status,
            assurance_level=(
                AssuranceLevel.A1_BOUNDED
                if status == ProofStatus.BOUNDED_NO_COUNTEREXAMPLE
                else AssuranceLevel.NONE
            ),
            engine=run["engine"],
            mode="BOUNDED",
            assumption_hash=assumption_hash,
            tcb_hash=tcb_hash,
            formula_hash=run["formula_hash"],
            bound=bound if status == ProofStatus.BOUNDED_NO_COUNTEREXAMPLE else None,
            artifact_refs=artifacts,
            counterexample_id=counterexample_id,
            diagnostics=tuple(diagnostics),
        )
        committed = self.store.commit_run(
            scope, run_id, worker_id, token, result
        )
        committed["localEvidence"] = evidence
        return committed

    @staticmethod
    def _evaluate(
        kind: str, evaluation: dict[str, Any]
    ) -> tuple[ProofStatus, dict[str, Any] | None, dict[str, Any], list[str]]:
        if kind == "EXACT_EQUALITY":
            if "expected" not in evaluation or "actual" not in evaluation:
                raise LocalEvaluationError(
                    "EXACT_EQUALITY requires expected and actual observations"
                )
            equal = canonical_json(evaluation["expected"]) == canonical_json(
                evaluation["actual"]
            )
            counterexample = None if equal else {
                "expected": evaluation["expected"],
                "actual": evaluation["actual"],
            }
            bound = {"scope": 1, "observations": 1}
        elif kind == "TRACE_EQUIVALENCE":
            source = evaluation.get("sourceTrace")
            target = evaluation.get("targetTrace")
            if not isinstance(source, list) or not isinstance(target, list):
                raise LocalEvaluationError(
                    "TRACE_EQUIVALENCE requires sourceTrace and targetTrace arrays"
                )
            if len(source) > 100_000 or len(target) > 100_000:
                raise LocalEvaluationError("trace exceeds the local event bound")
            equal = canonical_json(source) == canonical_json(target)
            first_difference = next(
                (index for index, pair in enumerate(zip(source, target)) if pair[0] != pair[1]),
                min(len(source), len(target)),
            )
            counterexample = None if equal else {
                "firstDifferentIndex": first_difference,
                "source": source[first_difference] if first_difference < len(source) else None,
                "target": target[first_difference] if first_difference < len(target) else None,
            }
            bound = {
                "scope": 1,
                "sourceEvents": len(source),
                "targetEvents": len(target),
            }
        else:
            samples = evaluation.get("samples")
            if not isinstance(samples, list) or not samples:
                raise LocalEvaluationError(
                    "PREDICATE_SAMPLES requires a non-empty samples array"
                )
            if len(samples) > 100_000:
                raise LocalEvaluationError("sample count exceeds the local bound")
            failures = []
            for index, sample in enumerate(samples):
                if not isinstance(sample, dict) or not isinstance(sample.get("holds"), bool):
                    raise LocalEvaluationError(
                        f"samples[{index}] must be an object with boolean holds"
                    )
                if not sample["holds"]:
                    failures.append(
                        {"index": index, "witness": sample.get("witness")}
                    )
            equal = not failures
            counterexample = None if equal else failures[0]
            bound = {"scope": 1, "samples": len(samples)}

        status = (
            ProofStatus.BOUNDED_NO_COUNTEREXAMPLE
            if equal
            else ProofStatus.REFUTED_WITH_COUNTEREXAMPLE
        )
        diagnostics = [
            "finite data-only evaluation; no universal or solver proof claimed"
        ]
        return status, counterexample, bound, diagnostics


__all__ = ["LocalBoundedExecutor", "LocalEvaluationError"]
