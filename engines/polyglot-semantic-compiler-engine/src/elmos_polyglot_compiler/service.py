"""Fail-closed service facade for the Polyglot Semantic Compiler.

The repository-owned engine is a local control plane. It loads only the
digest-bound compiled catalog and can prepare content-addressed plans, but it
does not contain native language adapters, an SMT solver, a fuzz runner, or a
certification authority. This module deliberately keeps those external
effects and their evidence in ``NOT_RUN`` / ``NOT_CERTIFIED`` state.
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
import hashlib
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from .catalog import CompiledCatalog, load_catalog
from .contracts import ExecutionAuthority, RuntimeRequest, digest_json
from .models import (
    CertificationRun,
    CertificationState,
    ObligationStatus,
    ProofObligation,
    RouteCell,
    VerdictStatus,
)

if TYPE_CHECKING:
    from .runtime import SkillRuntime


IMPLEMENTATION_STATE = "CODE_COMPLETE_LOCAL_CONTROL_PLANE"
NOT_RUN = "NOT_RUN"
NOT_CERTIFIED = "NOT_CERTIFIED"
ENGINE_NAME = "ELMOS Polyglot Repository Semantic Compiler"
ENGINE_VERSION = "3.0.0"

_CERTIFICATION_EVIDENCE = (
    "IMMUTABLE_SOURCE_AND_TARGET_ARTIFACTS",
    "SOURCE_NATIVE_BUILD_AND_RUNTIME",
    "TARGET_NATIVE_BUILD_AND_RUNTIME",
    "INDEPENDENT_HOLDOUT_CORPUS",
    "FORMAL_PROOF_RECEIPTS",
    "DIFFERENTIAL_FUZZING_RECEIPTS",
    "OBSERVABLE_BEHAVIOR_ORACLE_RECEIPTS",
    "INDEPENDENT_VERIFICATION",
    "SIGNED_CERTIFICATION_DECISION",
)


class ServiceError(ValueError):
    """The local service could not safely prepare or execute a request."""


def _bounded_text(value: Any, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ServiceError(f"{label} must be a non-empty string")
    if len(value.encode("utf-8")) > maximum:
        raise ServiceError(f"{label} exceeds the bounded size")
    return value


def _text_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _index_raw_records(value: Any) -> Mapping[str, Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return MappingProxyType({})
    indexed: dict[str, Mapping[str, Any]] = {}
    for row in value:
        if not isinstance(row, Mapping):
            continue
        identity = row.get("name") or row.get("id") or row.get("surface_id")
        if isinstance(identity, str) and identity:
            indexed[identity] = MappingProxyType(dict(row))
    return MappingProxyType(indexed)


class PolyglotSemanticCompilerService:
    """Read-only catalog and conservative planning facade.

    A :class:`SkillRuntime` may be attached by the trusted host. The facade
    never constructs execution authority, never creates an implicit state
    store, and never converts a plan into evidence. Runtime requests are
    delegated only with the caller-supplied :class:`ExecutionAuthority`.
    """

    def __init__(
        self,
        catalog: CompiledCatalog | None = None,
        *,
        runtime: SkillRuntime | None = None,
    ) -> None:
        # load_catalog verifies canonical bytes and the companion SHA-256. There
        # is intentionally no source-manifest fallback.
        self.catalog = catalog or load_catalog()
        if runtime is not None and runtime.catalog.digest != self.catalog.digest:
            raise ServiceError("attached runtime catalog digest differs")
        self.runtime = runtime

        # Compatibility views are derived only from the compiled catalog.
        self.skills_registry = MappingProxyType(
            {item.name: MappingProxyType(item.to_dict()) for item in self.catalog.skills}
        )
        self.technology_surfaces = _index_raw_records(
            self.catalog.raw.get("technologies")
        )
        self.repository_surfaces = _index_raw_records(
            self.catalog.raw.get("repository_surfaces")
        )
        self.certification_plans = self.catalog.reference_routes_by_id
        self.route_cells = self.catalog.routes_by_id

        pair_index: dict[tuple[str, str], RouteCell] = {}
        alias_index: dict[str, RouteCell] = {}
        for route in self.catalog.routes:
            pair = (
                route.source_language.casefold(),
                route.target_language.casefold(),
            )
            if pair in pair_index:
                raise ServiceError("compiled catalog contains a duplicate route pair")
            pair_index[pair] = route
            aliases = {
                route.route_id,
                f"{route.source_language}_to_{route.target_language}",
                f"{route.source_language}-to-{route.target_language}",
                f"route-{route.source_language}-{route.target_language}",
            }
            for alias in aliases:
                normalized = alias.casefold()
                previous = alias_index.get(normalized)
                if previous is not None and previous.route_id != route.route_id:
                    raise ServiceError("compiled catalog route aliases are ambiguous")
                alias_index[normalized] = route
        self._routes_by_pair = MappingProxyType(pair_index)
        self._route_aliases = MappingProxyType(alias_index)

    def execute_skill(
        self,
        skill_name: str,
        request: RuntimeRequest | Mapping[str, Any],
        *,
        authority: ExecutionAuthority,
    ) -> dict[str, Any]:
        """Delegate an exact request to an explicitly attached runtime."""

        if self.runtime is None:
            raise ServiceError("a trusted host must attach SkillRuntime explicitly")
        request_value = request.to_dict() if isinstance(request, RuntimeRequest) else request
        return self.runtime.execute(skill_name, request_value, authority=authority)

    def _route_for_pair(self, source: str, target: str) -> RouteCell:
        source = _bounded_text(source, "source_language", maximum=64)
        target = _bounded_text(target, "target_language", maximum=64)
        route = self._routes_by_pair.get((source.casefold(), target.casefold()))
        if route is None:
            raise ServiceError("requested directional route is absent from the compiled catalog")
        return route

    def _route_for_id(self, route_id: str) -> RouteCell:
        route_id = _bounded_text(route_id, "route_id", maximum=200)
        route = self._route_aliases.get(route_id.casefold())
        if route is None:
            raise ServiceError("route_id is absent from the compiled catalog")
        return route

    def get_compiler_status(self) -> dict[str, Any]:
        """Return implementation state without promoting execution evidence."""

        batch_counts = Counter(item.batch.value for item in self.catalog.skills)
        dependency_edges = sum(len(item.dependencies) for item in self.catalog.skills)
        source = self.catalog.raw.get("source")
        source_digest = source.get("archive_sha256") if isinstance(source, Mapping) else None
        return {
            "engine": ENGINE_NAME,
            "version": ENGINE_VERSION,
            "status": IMPLEMENTATION_STATE,
            "implementation": IMPLEMENTATION_STATE,
            "catalog_state": "DIGEST_VERIFIED",
            "catalog_digest": self.catalog.digest,
            "source_archive_sha256": source_digest,
            "runtime_attached": self.runtime is not None,
            "counts": {
                "batches": len(batch_counts),
                "skills": len(self.catalog.skills),
                "dependency_edges": dependency_edges,
                "technology_surfaces": len(self.technology_surfaces),
                "repository_surfaces": len(self.repository_surfaces),
                "route_cells": len(self.catalog.routes),
                "reference_routes": len(self.catalog.reference_routes),
            },
            "batch_skill_counts": dict(sorted(batch_counts.items())),
            "native_runtime": NOT_RUN,
            "external_runtime": NOT_RUN,
            "formal_solver_execution": NOT_RUN,
            "differential_fuzzing_execution": NOT_RUN,
            "external_evidence": NOT_RUN,
            "independent_verification": NOT_RUN,
            "certification": NOT_CERTIFIED,
        }

    def get_catalog_skills(self, batch: str | None = None) -> list[dict[str, Any]]:
        """Return exact compiled Skill records with honest evidence state."""

        normalized_batch = batch.upper() if batch is not None else None
        records: list[dict[str, Any]] = []
        for definition in self.catalog.skills:
            if normalized_batch is not None and definition.batch.value != normalized_batch:
                continue
            records.append(
                {
                    **definition.to_dict(),
                    "implementation": IMPLEMENTATION_STATE,
                    "external_runtime": NOT_RUN,
                    "external_evidence": NOT_RUN,
                    "certification": NOT_CERTIFIED,
                    "catalog_digest": self.catalog.digest,
                }
            )
        return records

    def get_supported_routes(self) -> list[dict[str, Any]]:
        """Return declared route cells; declaration is not route qualification."""

        return [
            {
                **route.to_dict(),
                "readiness": NOT_RUN,
                "status": NOT_RUN,
                "external_runtime": NOT_RUN,
                "external_evidence": NOT_RUN,
                "certification": NOT_CERTIFIED,
                "catalog_digest": self.catalog.digest,
            }
            for route in self.catalog.routes
        ]

    def transform_snippet(
        self,
        source_language: str,
        target_language: str,
        source_code: str,
    ) -> dict[str, Any]:
        """Create a directional external-adapter plan without target code."""

        route = self._route_for_pair(source_language, target_language)
        source_code = _bounded_text(source_code, "source_code", maximum=4_194_304)
        source_digest = _text_digest(source_code)
        plan_digest = digest_json(
            {
                "kind": "external-adapter-transformation-plan",
                "catalog_digest": self.catalog.digest,
                "route_id": route.route_id,
                "source_digest": source_digest,
            }
        )
        return {
            "transformation_id": f"tx-plan-{plan_digest[-24:]}",
            "route_id": route.route_id,
            "source_language": route.source_language,
            "target_language": route.target_language,
            "source_code": source_code,
            "source_digest": source_digest,
            "target_code": None,
            "target_digest": None,
            "status": "EXTERNAL_ADAPTER_REQUIRED",
            "execution_state": NOT_RUN,
            "capability_mode": "EXTERNAL_ADAPTER_REQUIRED",
            "adapter_plan": {
                "directional_route": route.route_id,
                "required_inputs": [
                    "IMMUTABLE_SOURCE_ARTIFACT",
                    "EXACT_SOURCE_PROFILE",
                    "EXACT_TARGET_PROFILE",
                    "TYPED_SEMANTIC_IR",
                    "AUTHORIZED_ADAPTER",
                ],
                "required_outputs": [
                    "TARGET_ARTIFACT",
                    "SOURCE_MAP",
                    "SEMANTIC_GAP_RECORDS",
                    "BUILD_RECEIPT",
                    "RUNTIME_EVIDENCE",
                ],
                "certification_authority": False,
            },
            "implementation": IMPLEMENTATION_STATE,
            "external_runtime": NOT_RUN,
            "external_evidence": NOT_RUN,
            "certification": NOT_CERTIFIED,
            "missing_evidence": [
                "EXTERNAL_ADAPTER_EXECUTION",
                "TARGET_BUILD",
                "TARGET_RUNTIME",
                "INDEPENDENT_SEMANTIC_VERIFICATION",
            ],
            "catalog_digest": self.catalog.digest,
        }

    def check_smt_formula(
        self,
        formula: str,
        *,
        solver_family: str = "SMT_Z3",
        timeout_ms: int = 5_000,
    ) -> dict[str, Any]:
        """Create a proof obligation; no solver is executed by this service."""

        formula = _bounded_text(formula, "formula", maximum=1_048_576)
        solver_family = _bounded_text(
            solver_family,
            "solver_family",
            maximum=64,
        )
        if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool):
            raise ServiceError("timeout_ms must be an integer")
        if timeout_ms < 1 or timeout_ms > 3_600_000:
            raise ServiceError("timeout_ms must be between 1 and 3600000")
        formula_digest = _text_digest(formula)
        proof_digest = digest_json(
            {
                "formula_digest": formula_digest,
                "solver_family": solver_family,
                "timeout_ms": timeout_ms,
            }
        )
        proof = ProofObligation(
            proof_id=f"proof-{proof_digest[-24:]}",
            formula_digest=formula_digest,
            solver_family=solver_family,
            timeout_ms=timeout_ms,
            status=ObligationStatus.NOT_RUN,
        )
        return {
            **proof.to_dict(),
            "status": NOT_RUN,
            "execution_state": NOT_RUN,
            "solver_executed": False,
            "expected_evidence_type": f"formal-proof/{proof.proof_id}",
            "implementation": IMPLEMENTATION_STATE,
            "external_runtime": NOT_RUN,
            "external_evidence": NOT_RUN,
            "certification": NOT_CERTIFIED,
            "missing_evidence": [
                "AUTHORIZED_SOLVER_EXECUTION",
                "SOLVER_RECEIPT",
                "INDEPENDENT_PROOF_VERIFICATION",
            ],
            "catalog_digest": self.catalog.digest,
        }

    def run_differential_fuzzing(
        self,
        source_surface: str,
        target_surface: str,
        cases: int = 20,
    ) -> dict[str, Any]:
        """Create a fuzz campaign request; no cases are synthesized or run."""

        route = self._route_for_pair(source_surface, target_surface)
        if not isinstance(cases, int) or isinstance(cases, bool):
            raise ServiceError("cases must be an integer")
        if cases < 1 or cases > 1_000_000:
            raise ServiceError("cases must be between 1 and 1000000")
        fuzz_digest = digest_json(
            {
                "kind": "external-differential-fuzz-plan",
                "catalog_digest": self.catalog.digest,
                "route_id": route.route_id,
                "iterations_requested": cases,
            }
        )
        return {
            "fuzz_id": f"fuzz-plan-{fuzz_digest[-24:]}",
            "route_id": route.route_id,
            "iterations_requested": cases,
            "iterations_completed": 0,
            "iterations": 0,
            "divergences_found": 0,
            "undetermined_cases": 0,
            "verdict": VerdictStatus.UNDETERMINED.value,
            "results_digest": None,
            "completed_at": None,
            "status": NOT_RUN,
            "reason": "DIGEST_BOUND_EXECUTED_CASE_RESULTS_REQUIRED",
            "cases_requested": cases,
            "cases_run": 0,
            "implementation": IMPLEMENTATION_STATE,
            "external_runtime": NOT_RUN,
            "external_evidence": NOT_RUN,
            "certification": NOT_CERTIFIED,
            "missing_evidence": [
                "AUTHORIZED_SOURCE_RUNTIME",
                "AUTHORIZED_TARGET_RUNTIME",
                "DIGEST_BOUND_EXECUTED_CASE_RESULTS",
                "INDEPENDENT_CORPUS_ATTESTATION",
            ],
            "catalog_digest": self.catalog.digest,
        }

    def _conservative_certification_run(
        self,
        route: RouteCell,
        *,
        source_digest: str | None,
        target_digest: str | None,
    ) -> CertificationRun:
        batch_coverage = {
            batch: 0 for batch in sorted({item.batch.value for item in self.catalog.skills})
        }
        decision_material = {
            "schema_version": "1.0",
            "kind": "polyglot-route-certification-plan",
            "catalog_digest": self.catalog.digest,
            "route_id": route.route_id,
            "source_digest": source_digest,
            "target_digest": target_digest,
            "proved_obligations": 0,
            "verdict": VerdictStatus.UNDETERMINED.value,
            "certification": NOT_CERTIFIED,
            "missing_evidence": list(_CERTIFICATION_EVIDENCE),
        }
        plan_digest = digest_json(decision_material)
        return CertificationRun(
            certification_id=f"certification-plan-{plan_digest[-24:]}",
            route_id=route.route_id,
            batch_coverage=batch_coverage,
            total_obligations=len(self.catalog.skills),
            proved_obligations=0,
            counterexamples_found=0,
            overall_verdict=VerdictStatus.UNDETERMINED,
            receipt_digest=plan_digest,
            certification=CertificationState.NOT_CERTIFIED,
            missing_evidence=_CERTIFICATION_EVIDENCE,
        )

    def certify_route(
        self,
        source_lang: str,
        target_lang: str,
        source_code: str,
        target_code: str,
        route_id: str | None = None,
    ) -> CertificationRun:
        """Return a digest-bound, non-certifying decision for supplied artifacts."""

        route = self._route_for_pair(source_lang, target_lang)
        if route_id is not None and self._route_for_id(route_id).route_id != route.route_id:
            raise ServiceError("route_id does not match the requested language pair")
        source_code = _bounded_text(source_code, "source_code", maximum=4_194_304)
        target_code = _bounded_text(target_code, "target_code", maximum=4_194_304)
        return self._conservative_certification_run(
            route,
            source_digest=digest_json({"source_code": source_code}),
            target_digest=digest_json({"target_code": target_code}),
        )

    def certify_language_route(self, route_id: str) -> dict[str, Any]:
        """Prepare a route-level certification plan with no fabricated inputs."""

        route = self._route_for_id(route_id)
        run = self._conservative_certification_run(
            route,
            source_digest=None,
            target_digest=None,
        )
        reference = self.catalog.reference_routes_by_id.get(route.route_id)
        if reference is None:
            reference = next(
                (
                    item
                    for item in self.catalog.reference_routes
                    if item.source_language.casefold() == route.source_language.casefold()
                    and item.target_language.casefold() == route.target_language.casefold()
                ),
                None,
            )
        result = run.to_dict()
        result.update(
            {
                "status": NOT_CERTIFIED,
                "route": route.to_dict(),
                "reference_plan": (
                    {
                        "plan_id": reference.plan_id,
                        "route_id": reference.route_id,
                        "required_skills": list(reference.required_skills),
                        "required_labs": list(reference.required_labs),
                        "target_levels": list(reference.target_levels),
                        "status": NOT_RUN,
                    }
                    if reference is not None
                    else None
                ),
                "implementation": IMPLEMENTATION_STATE,
                "native_runtime": NOT_RUN,
                "external_runtime": NOT_RUN,
                "external_evidence": NOT_RUN,
                "independent_verification": NOT_RUN,
                "catalog_digest": self.catalog.digest,
            }
        )
        return result


@lru_cache(maxsize=1)
def _default_service() -> PolyglotSemanticCompilerService:
    # Lazy loading keeps package import side-effect free while ensuring each
    # public operation fails closed if compiled resources are unavailable.
    return PolyglotSemanticCompilerService()


def get_compiler_status() -> dict[str, Any]:
    return _default_service().get_compiler_status()


def get_supported_routes() -> list[dict[str, Any]]:
    return _default_service().get_supported_routes()


def transform_snippet(src_lang: str, tgt_lang: str, code: str) -> dict[str, Any]:
    return _default_service().transform_snippet(src_lang, tgt_lang, code)


def check_smt_formula(formula: str) -> dict[str, Any]:
    return _default_service().check_smt_formula(formula)


def run_differential_fuzzing(
    source_surface: str,
    target_surface: str,
    cases: int = 20,
) -> dict[str, Any]:
    return _default_service().run_differential_fuzzing(
        source_surface,
        target_surface,
        cases,
    )


def certify_language_route(route_id: str) -> dict[str, Any]:
    return _default_service().certify_language_route(route_id)


__all__ = [
    "ENGINE_NAME",
    "ENGINE_VERSION",
    "IMPLEMENTATION_STATE",
    "NOT_CERTIFIED",
    "NOT_RUN",
    "PolyglotSemanticCompilerService",
    "ServiceError",
    "certify_language_route",
    "check_smt_formula",
    "get_compiler_status",
    "get_supported_routes",
    "run_differential_fuzzing",
    "transform_snippet",
]
