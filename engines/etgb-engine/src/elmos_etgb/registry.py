"""Explicit v1.1 Skill registry and JSON-safe operation dispatch.

Every source Skill has an allowlisted operation surface. The registry is not a
generic prompt dispatcher: unsupported provider/runtime work is returned as an
explicit non-claimable result, while local control-plane operations execute
with typed inputs and fail-closed validation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from .adapters import EXTERNAL_ADAPTERS
from .benchmark import validate_hidden_test_boundary
from .budget import BudgetLedger, estimate_machine_eta
from .campaigns import metamorphic_relation, mutation_summary
from .candidate import freeze_candidate, load_spec
from .campaign import merge_release_results
from .checkpoint import CheckpointStore
from .contracts import compile_requirement, validate_domain_case
from .attestation import load_json_object
from .corpus import build_license_review_request, verify_license_reviews, verify_lock
from .evidence import EvidenceStore
from .external_harness import ExternalExecutionContext, ExternalHarnessRouter
from .harness import phase_plan
from .incidents import regression_from_incident
from .materializer import materialize
from .oracles import compare_json, compare_trace
from .orchestrator import build_plan, external_campaign_preflight, gate_profile, release_attestation_request, release_preflight, run_profile, select_cases
from .planner import build_external_canary_plan, select_plan_shard, validate_plan, validate_plan_scope
from .performance import evaluate_performance
from .policy import authorize, authority_digest
from .risk import select_risk_plan
from .scheduling import FairScheduler, TaskRequest
from .scoring import score_results
from .statistics import multi_seed_stability, non_inferiority, wilson_interval
from .supply_chain import inspect_tree
from .triage import cluster_failures
from .validation import coverage_report, load_cases, validate_package, validate_results


@dataclass(frozen=True)
class SkillDescriptor:
    name: str
    description: str
    dependencies: tuple[str, ...]


class SkillRegistry:
    """Bind all 50 exact source names to repository-owned handlers."""

    _OPERATIONS: dict[str, tuple[str, ...]] = {
        "etgb-orchestrator": ("plan", "canary_plan", "run", "merge_results", "score", "gate", "preflight", "campaign_preflight", "attestation_request", "eta", "stability", "triage"),
        "test-case-authoring": ("validate", "coverage", "materialized", "validate_case"),
        "spring-modernization-validation": ("validate_case", "capability"),
        "repository-translation-validation": ("validate_case", "capability"),
        "project-generation-validation": ("compile_requirement", "validate_case", "capability"),
        "sql-dialect-routine-validation": ("validate_case", "capability"),
        "differential-oracle-engine": ("compare_json", "compare_trace"),
        "metamorphic-fuzz-mutation": ("metamorphic", "mutation_summary", "property_campaign"),
        "corpus-governance": ("verify", "review_request", "review_verify"),
        "release-certification": ("gate", "preflight", "attestation_request"),
        "production-harness-integration": ("phase_plan", "harness_preflight", "campaign_preflight"),
        "environment-authority-sandbox": ("authorize", "authority_digest", "hidden_boundary"),
        "checkpoint-resume-recovery": ("verify_checkpoint", "resume_contract"),
        "evidence-provenance-ledger": ("verify_evidence",),
        "budget-cost-eta-governance": ("eta", "reserve", "consume", "reconcile"),
        "risk-based-test-selection": ("risk_plan",),
        "benchmark-integrity-hidden-tests": ("hidden_boundary",),
        "observability-failure-triage": ("triage",),
        "performance-scale-certification": ("performance",),
        "statistical-validity-reproducibility": ("stability", "wilson", "non_inferiority"),
        "supply-chain-artifact-security": ("inspect",),
        "incident-regression-learning": ("regression",),
        "multi-tenant-scheduling-isolation": ("schedule", "validate_plan", "select_shard"),
        "release-candidate-integrity": ("freeze",),
        "identity-access-tenant-validation": ("validate_case", "capability"),
        "platform-control-plane-validation": ("validate_case", "capability"),
        "repository-ingestion-context-validation": ("validate_case", "capability"),
        "multimodal-document-processing-validation": ("validate_case", "capability"),
        "ai-runtime-model-routing-validation": ("validate_case", "capability"),
        "agent-protocol-tooling-validation": ("validate_case", "capability"),
        "rag-memory-knowledge-validation": ("validate_case", "capability"),
        "project-intelligence-validation": ("validate_case", "capability"),
        "online-ide-debug-validation": ("validate_case", "capability"),
        "artifact-document-diagram-validation": ("validate_case", "capability"),
        "collaboration-integrations-validation": ("validate_case", "capability"),
        "billing-entitlements-validation": ("validate_case", "capability"),
        "payment-finance-validation": ("validate_case", "capability"),
        "api-sdk-webhook-validation": ("validate_case", "capability"),
        "storage-search-cache-validation": ("validate_case", "capability"),
        "deployment-operations-validation": ("validate_case", "capability"),
        "security-privacy-compliance-validation": ("validate_case", "capability"),
        "ui-accessibility-localization-validation": ("validate_case", "capability"),
        "analytics-admin-support-validation": ("validate_case", "capability"),
        "notifications-scheduler-validation": ("validate_case", "capability"),
        "ai-solution-factory-validation": ("validate_case", "capability"),
        "data-bigdata-solution-validation": ("validate_case", "capability"),
        "commercial-delivery-certification-validation": ("validate_case", "capability"),
        "product-journey-validation": ("validate_case", "capability"),
        "standards-assurance-validation": ("validate_case", "capability"),
        "full-product-coverage-governance": ("coverage", "feature_coverage", "surface_audit"),
    }

    def __init__(self, package_root: Path) -> None:
        self.package_root = package_root.resolve(strict=True)
        manifest = yaml.safe_load((self.package_root / "skills/manifest.yaml").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("skills manifest must be an object")
        self._skills = {
            str(item["name"]): SkillDescriptor(str(item["name"]), str(item.get("description", "")), tuple(str(value) for value in item.get("depends_on", [])))
            for item in manifest.get("skills", [])
        }
        missing = sorted(set(self._skills) - set(self._OPERATIONS))
        if missing:
            raise ValueError("unbound ETGB skills: " + ", ".join(missing))

    @property
    def skills(self) -> tuple[SkillDescriptor, ...]:
        return tuple(self._skills[name] for name in sorted(self._skills))

    def describe(self) -> list[dict[str, Any]]:
        return [{"name": skill.name, "description": skill.description, "depends_on": list(skill.dependencies), "operations": list(self._OPERATIONS[skill.name]), "runtime_state": "BOUND"} for skill in self.skills]

    @staticmethod
    def _results(payload: Mapping[str, Any], key: str = "results") -> list[dict[str, Any]]:
        value = payload.get(key)
        if value is None and payload.get(f"{key}_path"):
            value = [json.loads(line) for line in Path(str(payload[f"{key}_path"])).read_text(encoding="utf-8").splitlines() if line.strip()]
        if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
            raise ValueError(f"{key} requires a list or {key}_path")
        return [dict(item) for item in value]

    @staticmethod
    def _object(payload: Mapping[str, Any], key: str) -> dict[str, Any] | None:
        value = payload.get(key)
        if isinstance(value, Mapping):
            return dict(value)
        path = payload.get(f"{key}_path")
        return load_json_object(Path(str(path))) if path else None

    @staticmethod
    def _unavailable(skill: str, reason: str) -> dict[str, Any]:
        return {"skill": skill, "status": "EXTERNAL_ADAPTER_REQUIRED", "claimable": False, "reason": reason, "external_evidence": "NOT_RUN"}

    def dispatch(self, skill: str, operation: str, payload: Mapping[str, Any] | None = None) -> Any:
        if skill not in self._skills:
            raise KeyError(f"unknown ETGB skill: {skill}")
        if operation not in self._OPERATIONS[skill]:
            raise ValueError(f"operation '{operation}' is not allowed for {skill}")
        data = dict(payload or {})
        if operation == "validate":
            return validate_package(self.package_root, release=bool(data.get("release")), archive=Path(data["archive"]) if data.get("archive") else None, extracted=Path(data["extracted"]) if data.get("extracted") else None, trust_store=dict(data["trust_store"]) if isinstance(data.get("trust_store"), Mapping) else None, license_reviews_path=Path(str(data["license_reviews_path"])) if data.get("license_reviews_path") else None)
        if operation == "coverage":
            return coverage_report(self.package_root)
        if operation == "feature_coverage":
            from .features import feature_coverage_report
            return feature_coverage_report(self.package_root)
        if operation == "surface_audit":
            from .discovery import load_surface, surface_coverage_report
            surface_data = data.get("surface")
            if not surface_data and data.get("surface_path"):
                surface_data = load_surface(Path(str(data["surface_path"])))
            if not isinstance(surface_data, dict):
                raise ValueError("surface_audit requires surface dict or surface_path")
            return surface_coverage_report(self.package_root, surface_data)
        if operation == "materialized":
            return materialize(self.package_root)
        if operation == "validate_case":
            case = data.get("case")
            if not isinstance(case, Mapping):
                raise ValueError("case must be an object")
            errors = validate_domain_case(case)
            return {"valid": not errors, "errors": errors}
        if operation == "compile_requirement":
            return compile_requirement(data.get("requirement", ""), contract_id=str(data.get("contract_id", "REQ-ETGB")))
        if operation == "capability":
            return self._unavailable(skill, "real source/target runtime evidence is not provided by the offline package")
        if operation == "verify":
            return verify_lock(self.package_root, release=bool(data.get("release")), trust_store=dict(data["trust_store"]) if isinstance(data.get("trust_store"), Mapping) else None, license_reviews_path=Path(str(data["license_reviews_path"])) if data.get("license_reviews_path") else None)
        if operation == "review_request":
            return build_license_review_request(self.package_root)
        if operation == "review_verify":
            if not data.get("records_path") or not data.get("trust_store_path"):
                raise ValueError("review_verify requires records_path and trust_store_path")
            return verify_license_reviews(
                self.package_root,
                release=True,
                trust_store=load_json_object(Path(str(data["trust_store_path"]))),
                records_path=Path(str(data["records_path"])),
            )
        if operation == "compare_json":
            return compare_json(data.get("left"), data.get("right"), ignore_paths=data.get("ignore_paths", []), unordered_paths=data.get("unordered_paths", []), absolute_tolerance=float(data.get("absolute_tolerance", 0.0)), relative_tolerance=float(data.get("relative_tolerance", 0.0)))
        if operation == "compare_trace":
            return compare_trace(list(data.get("left", [])), list(data.get("right", [])), happens_before=data.get("happens_before", []))
        if operation == "property_campaign":
            return self._unavailable(skill, "callables are intentionally not accepted across the JSON dispatch boundary")
        if operation == "metamorphic":
            return metamorphic_relation(str(data.get("name", "unnamed")), data.get("left"), data.get("right"), relation=lambda left, right: left == right)
        if operation == "mutation_summary":
            return mutation_summary(list(data.get("mutants", [])), [bool(value) for value in data.get("killed", [])])
        if operation == "plan":
            repo_root = Path(str(data.get("repo_root", self.package_root.parents[2])))
            return build_plan(self.package_root, changed_from=data.get("changed_from"), root_for_git=repo_root, history_path=Path(data["history"]) if data.get("history") else None, max_cases=int(data.get("max_cases", 500)), seed=int(data.get("seed", 17)), shard_count=int(data.get("shards", 8)), candidate_digest=data.get("candidate_digest"), profile=data.get("profile"))
        if operation == "canary_plan":
            return build_external_canary_plan(
                self.package_root,
                candidate_digest=str(data.get("candidate_digest", "")),
                shard_count=int(data.get("shards", 1)),
            )
        if operation == "run":
            output = data.get("output")
            if not output:
                raise ValueError("run requires an explicit output path")
            plan_value = None
            plan_ids = set(str(value) for value in data.get("case_ids", [])) or None
            if isinstance(data.get("plan"), Mapping) or data.get("plan_path"):
                plan_value = dict(data["plan"]) if isinstance(data.get("plan"), Mapping) else load_json_object(Path(str(data["plan_path"])))
                profile = str(data.get("profile", "smoke"))
                plan_errors = validate_plan_scope(self.package_root, plan_value) if profile in {"release", "golden", "release-canary"} else validate_plan(plan_value)
                if plan_errors:
                    raise ValueError("invalid run plan: " + "; ".join(plan_errors))
                plan_ids = select_plan_shard(plan_value, int(data["shard_id"])) if data.get("shard_id") is not None else set(plan_value["case_ids"])
            profile = str(data.get("profile", "smoke"))
            case_profile = "release" if profile == "release-canary" else profile
            selected = select_cases(self.package_root, profile=case_profile, business_line=data.get("business_line"), priority=data.get("priority"), case_id=data.get("case_id"), plan_ids=plan_ids, limit=int(data["limit"]) if data.get("limit") is not None else None)
            candidate = dict(data["candidate"]) if isinstance(data.get("candidate"), Mapping) else (load_spec(Path(str(data["candidate"]))) if data.get("candidate") else None)
            trust_store = dict(data["trust_store"]) if isinstance(data.get("trust_store"), Mapping) else (load_json_object(Path(str(data["trust_store_path"]))) if data.get("trust_store_path") else None)
            role_assignment = self._object(data, "role_assignment")
            production_authority = self._object(data, "production_authority")
            external_router = None
            external_context = None
            if data.get("harness_config"):
                context = data.get("external_context")
                if not isinstance(context, Mapping) or not isinstance(plan_value, Mapping) or not isinstance(candidate, Mapping):
                    raise ValueError("external run requires plan_path, candidate, and external_context")
                if plan_value.get("candidate_digest") != candidate.get("candidate_digest"):
                    raise ValueError("plan and frozen candidate digest do not match")
                external_router = ExternalHarnessRouter.load(Path(str(data["harness_config"])))
                external_context = ExternalExecutionContext(
                    tenant_id=str(context["tenant_id"]),
                    project_id=str(context["project_id"]),
                    task_id=str(context["task_id"]),
                    candidate_digest=str(candidate["candidate_digest"]),
                    plan_digest=str(plan_value["plan_digest"]),
                    environment_id=str(context["environment_id"]),
                    authority_id=str(context["authority_id"]),
                    owner_id=str(context["owner_id"]),
                    fencing_token=int(context["fencing_token"]),
                    checkpoint_digest=str(context["checkpoint_digest"]),
                )
            results, score = run_profile(
                self.package_root,
                selected,
                profile=profile,
                output=Path(str(output)).resolve(),
                state_db=Path(str(data["state_db"])).resolve() if data.get("state_db") else None,
                artifact_root=Path(str(data["artifact_root"])).resolve() if data.get("artifact_root") else None,
                allow_unavailable=bool(data.get("allow_unavailable")),
                owner=data.get("owner"),
                run_id=data.get("run_id"),
                resume=bool(data.get("resume")),
                candidate=candidate,
                external_router=external_router,
                external_context=external_context,
                trust_store=trust_store,
                license_reviews_path=Path(str(data["license_reviews_path"])) if data.get("license_reviews_path") else None,
                plan=plan_value,
                role_assignment=role_assignment,
                production_authority=production_authority,
            )
            return {"selected": len(selected), "results": results, "score": score}
        if operation == "score":
            results = self._results(data)
            errors = validate_results(results, self.package_root)
            if errors:
                raise ValueError(f"invalid results: {errors[:3]}")
            return score_results(results, self.package_root, expected_count=int(data["expected_count"]) if data.get("expected_count") is not None else None, complete=bool(data["complete"]) if "complete" in data else None, corpus_release=bool(data.get("release")), trust_store=dict(data["trust_store"]) if isinstance(data.get("trust_store"), Mapping) else None, license_reviews_path=Path(str(data["license_reviews_path"])) if data.get("license_reviews_path") else None)
        if operation == "merge_results":
            if not isinstance(data.get("plan"), Mapping) or not isinstance(data.get("result_paths"), list) or not isinstance(data.get("trust_store"), Mapping):
                raise ValueError("merge_results requires plan, result_paths, and trust_store")
            _, receipt = merge_release_results(self.package_root, data["plan"], [Path(str(value)) for value in data["result_paths"]], candidate_digest=str(data["candidate_digest"]), trust_store=data["trust_store"])
            return receipt
        if operation == "gate":
            results = self._results(data)
            return gate_profile(self.package_root, results, profile=str(data.get("profile", "release")), external_attested=bool(data.get("external_attested")), independent_verifier=data.get("independent_verifier"), external_attestation=dict(data["external_attestation"]) if isinstance(data.get("external_attestation"), Mapping) else None, trust_store=dict(data["trust_store"]) if isinstance(data.get("trust_store"), Mapping) else None, candidate_digest=data.get("candidate_digest"), license_reviews_path=Path(str(data["license_reviews_path"])) if data.get("license_reviews_path") else None, plan=dict(data["plan"]) if isinstance(data.get("plan"), Mapping) else None, role_assignment=self._object(data, "role_assignment"), production_authority=self._object(data, "production_authority"))
        if operation == "preflight":
            return release_preflight(self.package_root, profile=str(data.get("profile", "release")), results=self._results(data) if data.get("results") is not None or data.get("results_path") else None, candidate_digest=data.get("candidate_digest"), trust_store=dict(data["trust_store"]) if isinstance(data.get("trust_store"), Mapping) else None, license_reviews_path=Path(str(data["license_reviews_path"])) if data.get("license_reviews_path") else None, plan=dict(data["plan"]) if isinstance(data.get("plan"), Mapping) else None)
        if operation == "attestation_request":
            return release_attestation_request(self.package_root, self._results(data), profile=str(data.get("profile", "release")), candidate_digest=data.get("candidate_digest"), trust_store=dict(data["trust_store"]) if isinstance(data.get("trust_store"), Mapping) else None, license_reviews_path=Path(str(data["license_reviews_path"])) if data.get("license_reviews_path") else None, plan=dict(data["plan"]) if isinstance(data.get("plan"), Mapping) else None, role_assignment=self._object(data, "role_assignment"), production_authority=self._object(data, "production_authority"))
        if operation == "campaign_preflight":
            required = ("candidate", "plan", "config_path", "trust_store", "tenant_id", "project_id", "task_id", "environment_id", "authority_id", "owner_ids")
            missing = [field for field in required if not data.get(field)]
            if missing:
                raise ValueError("campaign_preflight requires " + ", ".join(missing))
            if not isinstance(data["candidate"], Mapping) or not isinstance(data["plan"], Mapping) or not isinstance(data["trust_store"], Mapping) or not isinstance(data["owner_ids"], list):
                raise ValueError("campaign_preflight candidate, plan, trust_store, and owner_ids have invalid types")
            return external_campaign_preflight(
                self.package_root,
                candidate=dict(data["candidate"]),
                plan=dict(data["plan"]),
                router=ExternalHarnessRouter.load(Path(str(data["config_path"]))),
                role_assignment=self._object(data, "role_assignment"),
                production_authority=self._object(data, "production_authority"),
                trust_store=dict(data["trust_store"]),
                license_reviews_path=Path(str(data["license_reviews_path"])) if data.get("license_reviews_path") else None,
                tenant_id=str(data["tenant_id"]),
                project_id=str(data["project_id"]),
                task_id=str(data["task_id"]),
                environment_id=str(data["environment_id"]),
                authority_id=str(data["authority_id"]),
                owner_ids=[str(value) for value in data["owner_ids"]],
            )
        if operation == "eta":
            cases = data.get("cases")
            if cases is None and data.get("plan_path"):
                plan = json.loads(Path(str(data["plan_path"])).read_text(encoding="utf-8")); cases = select_cases(self.package_root, plan_ids=set(plan.get("case_ids", [])))
            if not isinstance(cases, list):
                cases = list(load_cases(self.package_root))
            history = data.get("history", [])
            if isinstance(history, str):
                history = [json.loads(line) for line in Path(history).read_text(encoding="utf-8").splitlines() if line.strip()]
            return estimate_machine_eta(cases, history, concurrency=int(data.get("concurrency", 3)))
        if operation == "stability":
            return multi_seed_stability(self._results(data))
        if operation == "triage":
            return cluster_failures(self._results(data))
        if operation == "phase_plan":
            return [{"from": source.value, "phase": phase, "to": target.value} for source, phase, target in phase_plan(data)]
        if operation == "harness_preflight":
            if not data.get("config_path"):
                raise ValueError("harness_preflight requires config_path")
            if isinstance(data.get("required_adapters"), list):
                required_adapters = {str(value) for value in data["required_adapters"]}
            else:
                plan = data.get("plan")
                if isinstance(plan, Mapping):
                    plan_errors = validate_plan_scope(self.package_root, dict(plan))
                    if plan_errors:
                        raise ValueError("invalid Harness preflight plan: " + "; ".join(plan_errors))
                    planned_ids = set(str(value) for value in plan.get("case_ids", []))
                else:
                    planned_ids = {str(case["id"]) for case in load_cases(self.package_root)}
                required_adapters = {
                    str(case.get("execution", {}).get("adapter", ""))
                    for case in load_cases(self.package_root)
                    if str(case.get("id")) in planned_ids and str(case.get("execution", {}).get("adapter", "")) in EXTERNAL_ADAPTERS
                }
            production_transport = bool(data.get("production")) or (
                isinstance(data.get("plan"), Mapping)
                and data["plan"].get("profile") in {"release", "golden", "release-canary"}
            )
            return ExternalHarnessRouter.load(Path(str(data["config_path"]))).capability_report(
                required_adapters,
                require_production_transport=production_transport,
            )
        if operation == "authorize":
            authority = data.get("authority")
            request = data.get("request")
            if not isinstance(authority, Mapping) or not isinstance(request, Mapping):
                raise ValueError("authorize requires authority and request objects")
            return authorize(dict(authority), dict(request)).as_dict()
        if operation == "authority_digest":
            authority = data.get("authority")
            if not isinstance(authority, Mapping):
                raise ValueError("authority must be an object")
            return {"digest": authority_digest(dict(authority))}
        if operation == "hidden_boundary":
            return validate_hidden_test_boundary(data.get("public_paths", []), data.get("hidden_paths", []), worker_role=str(data.get("worker_role", "orchestrator")))
        if operation == "verify_checkpoint":
            directory = Path(str(data.get("directory", data.get("checkpoint_root", ""))))
            if not str(directory):
                raise ValueError("checkpoint directory is required")
            return CheckpointStore(directory).verify(str(data["run_id"]))
        if operation == "resume_contract":
            return CheckpointStore(Path(str(data["directory"]))).resume_contract(str(data["run_id"]), candidate_digest=str(data["candidate_digest"]), plan_digest=str(data["plan_digest"]), current_fencing_token=int(data["current_fencing_token"]))
        if operation == "verify_evidence":
            store = EvidenceStore(Path(str(data["directory"])), hmac_key=str(data["hmac_key"]).encode() if data.get("hmac_key") else None)
            return store.verify()
        if operation in {"reserve", "consume", "reconcile"}:
            ledger = BudgetLedger(Path(str(data["ledger"])))
            if operation == "reserve":
                return ledger.reserve(run_id=str(data["run_id"]), tenant_id=str(data["tenant_id"]), owner_id=str(data["owner_id"]), max_input_tokens=int(data.get("max_input_tokens", 0)), max_output_tokens=int(data.get("max_output_tokens", 0)), max_credit_usd=float(data.get("max_credit_usd", 0)), max_wall_clock_ms=int(data.get("max_wall_clock_ms", 0)))
            if operation == "consume":
                return ledger.consume(run_id=str(data["run_id"]), idempotency_key=str(data["idempotency_key"]), phase=str(data["phase"]), input_tokens=int(data.get("input_tokens", 0)), output_tokens=int(data.get("output_tokens", 0)), credit_usd=float(data.get("credit_usd", 0)), wall_clock_ms=int(data.get("wall_clock_ms", 0)))
            return ledger.reconcile(str(data["run_id"]))
        if operation == "risk_plan":
            cases = data.get("cases", list(load_cases(self.package_root)))
            return select_risk_plan(cases, affected_lines=set(data.get("affected_lines", [])), historical_results=data.get("historical_results", []), max_cases=int(data.get("max_cases", 500)), seed=int(data.get("seed", 17)))
        if operation == "performance":
            return evaluate_performance(dict(data.get("candidate", {})), dict(data.get("budgets", {})), baseline=dict(data.get("baseline", {})))
        if operation == "wilson":
            lower, upper = wilson_interval(int(data["successes"]), int(data["trials"]))
            return {"lower": lower, "upper": upper}
        if operation == "non_inferiority":
            return non_inferiority(int(data["candidate_successes"]), int(data["candidate_trials"]), int(data["baseline_successes"]), int(data["baseline_trials"]), margin=float(data["margin"]))
        if operation == "inspect":
            return inspect_tree(Path(str(data["root"])))
        if operation == "regression":
            incident = data.get("incident")
            if not isinstance(incident, Mapping):
                raise ValueError("incident must be an object")
            return regression_from_incident(incident)
        if operation == "schedule":
            scheduler = FairScheduler(max_active_per_account=int(data.get("max_active_per_account", 3)))
            requests = data.get("requests", [])
            if not isinstance(requests, list):
                raise ValueError("requests must be a list")
            for value in requests:
                if not isinstance(value, Mapping):
                    raise ValueError("each scheduling request must be an object")
                scheduler.enqueue(TaskRequest(task_id=str(value["task_id"]), tenant_id=str(value["tenant_id"]), account_id=str(value["account_id"]), priority=int(value.get("priority", 0))))
            dispatched = []
            while True:
                item = scheduler.dispatch(account_id=data.get("account_id"), tenant_id=data.get("tenant_id"))
                if item is None:
                    break
                dispatched.append(item)
            return {"dispatched": dispatched, "snapshot": scheduler.snapshot()}
        if operation == "validate_plan":
            plan = data.get("plan")
            errors = validate_plan_scope(self.package_root, plan) if isinstance(plan, Mapping) and plan.get("profile") in {"release", "golden", "release-canary"} else validate_plan(plan)
            return {"valid": not errors, "errors": errors}
        if operation == "select_shard":
            plan = data.get("plan")
            if isinstance(plan, Mapping) and plan.get("profile") in {"release", "golden", "release-canary"}:
                errors = validate_plan_scope(self.package_root, plan)
                if errors:
                    raise ValueError("invalid protected plan: " + "; ".join(errors))
            return {"case_ids": sorted(select_plan_shard(plan, int(data["shard_id"])))}
        if operation == "freeze":
            candidate = data.get("candidate")
            if not isinstance(candidate, Mapping):
                raise ValueError("candidate must be an object")
            return freeze_candidate(dict(candidate))
        raise AssertionError(operation)
