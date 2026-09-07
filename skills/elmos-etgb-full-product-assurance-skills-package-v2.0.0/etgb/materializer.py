from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import yaml

GENERATED_AT = "2026-08-28"
PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _short(value: str, length: int = 14) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _combined_priority(*priorities: str) -> str:
    return max(priorities, key=lambda p: PRIORITY_RANK[p])


def _profiles(priority: str, level: str) -> list[str]:
    if priority == "P0":
        out = ["pr", "nightly", "release"]
    elif priority == "P1":
        out = ["nightly", "weekly", "release"]
    else:
        out = ["weekly", "release", "exhaustive"]
    if level in {"L3", "L4"} and "golden" not in out:
        out.append("golden")
    return out


def _oracle_set(primary: str, priority: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [
        {"type": "static-structure-contract", "critical": priority == "P0"},
        {"type": "build-and-test-success", "critical": priority == "P0"},
        {"type": primary, "critical": priority in {"P0", "P1"}},
        {"type": "unsupported-feature-disclosure", "critical": True},
    ]
    if "security" in primary:
        out.append({"type": "security-negative-oracle", "critical": True})
    if any(x in primary for x in ["state", "transaction", "side-effect"]):
        out.append({"type": "state-side-effect-diff", "critical": priority == "P0"})
    if "performance" in primary or "cost" in primary or "operational" in primary:
        out.append({"type": "performance-budget", "critical": False})
    return out


def _base_case(
    *, case_id: str, title: str, line: str, family: str, level: str, priority: str,
    source: dict[str, Any], target: dict[str, Any], capability_id: str,
    dimensions: dict[str, Any], primary_oracle: str, tags: Iterable[str],
    execution: dict[str, Any], requirement_text: str, provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    forbidden = [
        "silent semantic loss", "undocumented manual intervention", "false success claim",
        "data corruption", "unbounded privilege expansion"
    ]
    if "security" in family or "security" in primary_oracle:
        forbidden += ["authentication bypass", "authorization weakening", "secret exposure"]
    return {
        "schema_version": "1.0",
        "id": case_id,
        "title": title,
        "business_line": line,
        "family": family,
        "level": level,
        "priority": priority,
        "profiles": _profiles(priority, level),
        "tags": sorted(set(tags)),
        "source": source,
        "target": target,
        "requirements": [{"id": f"REQ-{_short(case_id, 10).upper()}", "text": requirement_text, "critical": priority == "P0"}],
        "execution": execution,
        "oracles": _oracle_set(primary_oracle, priority),
        "coverage": {"capability_id": capability_id, "dimensions": dimensions},
        "forbidden_differences": forbidden,
        "gates": {
            "claim_policy": "must-pass" if priority in {"P0", "P1"} else "manual-approval",
            "silent_semantic_error_allowed": False,
            "evidence_required": True,
        },
        "provenance": {"kind": "generated-matrix", "generated_at": GENERATED_AT, **(provenance or {})},
    }


def _load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def spring_cases(root: Path) -> Iterable[dict[str, Any]]:
    matrix = _load(root / "matrices/spring-modernization.yaml")
    for archetype in matrix["archetypes"]:
        traits = set(archetype["traits"])
        for feat in matrix["features"]:
            required = set(feat.get("requires_any", []))
            if required and not (traits & required):
                continue
            for variant in matrix["variants"]:
                token = f"{archetype['id']}|{feat['id']}|{variant}"
                case_id = f"SM-{_slug(feat['group']).upper()}-{_short(token).upper()}"
                yield _base_case(
                    case_id=case_id,
                    title=f"{archetype['title']} → Spring Boot 4: {feat['title']} [{variant}]",
                    line="spring-modernization", family=feat["group"], level=feat["level"], priority=feat["priority"],
                    source={"archetype": archetype["id"], "traits": archetype["traits"], **archetype.get("source", {})},
                    target={"framework": "Spring Boot 4", "java": "21+", **archetype.get("target", {})},
                    capability_id=f"SM.{feat['id']}",
                    dimensions={"archetype": archetype["id"], "feature": feat["id"], "variant": variant},
                    primary_oracle=feat["default_oracles"][0], tags=["spring", "modernization", variant, *traits],
                    execution={
                        "adapter": "external-transformation-harness", "timeout_seconds": 3600,
                        "phases": ["inventory", "baseline", "transform", "build", "dual-run", "state-diff", "report"],
                        "fixture_selector": {"archetype": archetype["id"], "capability": feat["id"], "variant": variant},
                    },
                    requirement_text=f"Preserve the observable semantics of {feat['title']} while modernizing {archetype['title']} to Spring Boot 4.",
                    provenance={"matrix_id": matrix["matrix_id"]},
                )


def cross_language_cases(root: Path) -> Iterable[dict[str, Any]]:
    matrix = _load(root / "matrices/cross-language.yaml")
    for pair in matrix["pairs"]:
        kind = pair["kind"]
        for feat in matrix["features"]:
            required = set(feat.get("requires_any", []))
            if required and kind not in required:
                continue
            for variant in matrix["variants"]:
                priority = _combined_priority(pair["tier"], feat["priority"])
                token = f"{pair['id']}|{feat['id']}|{variant}"
                case_id = f"XLC-{_slug(feat['group']).upper()}-{_short(token).upper()}"
                yield _base_case(
                    case_id=case_id,
                    title=f"{pair['source']} → {pair['target']}: {feat['title']} [{variant}]",
                    line="cross-language", family=feat["group"], level=feat["level"], priority=priority,
                    source={"language_or_stack": pair["source"], "repository_kind": kind},
                    target={"language_or_stack": pair["target"], "repository_kind": kind},
                    capability_id=f"XLC.{feat['id']}",
                    dimensions={"pair": pair["id"], "feature": feat["id"], "variant": variant},
                    primary_oracle=feat["default_oracles"][0], tags=["repository-translation", kind, variant, pair["source"], pair["target"]],
                    execution={
                        "adapter": "external-repository-translation-harness", "timeout_seconds": 5400,
                        "phases": ["inventory", "source-baseline", "translate", "target-build", "differential-execute", "state-diff", "report"],
                        "fixture_selector": {"pair": pair["id"], "capability": feat["id"], "variant": variant},
                        "random_seeds": [17, 43, 101],
                    },
                    requirement_text=f"Translate the complete repository from {pair['source']} to {pair['target']} while preserving {feat['title']} semantics.",
                    provenance={"matrix_id": matrix["matrix_id"]},
                )


def project_generation_cases(root: Path) -> Iterable[dict[str, Any]]:
    matrix = _load(root / "matrices/project-generation.yaml")
    for stack in matrix["stacks"]:
        for template in matrix["templates"]:
            for deployment in matrix["deployment_profiles"]:
                priority = _combined_priority(stack["tier"], template["priority"])
                token = f"{stack['id']}|{template['id']}|{deployment}"
                case_id = f"PG-BASE-{_short(token).upper()}"
                yield _base_case(
                    case_id=case_id,
                    title=f"Generate {template['title']} with {stack['framework']} [{deployment}]",
                    line="project-generation", family=template["group"], level="L2", priority=priority,
                    source={"requirement_contract": template["id"], "mode": "greenfield"},
                    target={"stack": stack["id"], "language": stack["language"], "framework": stack["framework"], "deployment": deployment},
                    capability_id=f"PG.{template['id']}",
                    dimensions={"stack": stack["id"], "template_or_change": template["id"], "deployment_or_mode": deployment},
                    primary_oracle="requirement-executable-acceptance-and-quality", tags=["project-generation", "greenfield", deployment, stack["language"]],
                    execution={
                        "adapter": "external-project-generation-harness", "timeout_seconds": 5400,
                        "phases": ["requirements", "assumptions", "architecture", "generate", "build", "acceptance", "security", "performance", "report"],
                        "contract_selector": template["id"], "random_seeds": [17, 43, 101],
                    },
                    requirement_text=f"Generate a deployable {template['title']} implementation in {stack['framework']} and satisfy all executable acceptance tests.",
                    provenance={"matrix_id": matrix["matrix_id"]},
                )
        for change in matrix["evolution_tasks"]:
            token = f"{stack['id']}|evolution|{change}"
            case_id = f"PG-EVO-{_short(token).upper()}"
            yield _base_case(
                case_id=case_id,
                title=f"Evolve {stack['framework']}: {change}",
                line="project-generation", family="evolution", level="L3", priority=_combined_priority(stack["tier"], "P1"),
                source={"mode": "existing-generated-repository", "baseline": "version-n"},
                target={"stack": stack["id"], "change": change, "version": "n+1"},
                capability_id=f"PG.evolution.{_slug(change)}",
                dimensions={"stack": stack["id"], "template_or_change": _slug(change), "deployment_or_mode": "incremental-evolution"},
                primary_oracle="old-and-new-acceptance-regression-equivalence", tags=["project-generation", "evolution", stack["language"]],
                execution={"adapter": "external-project-evolution-harness", "timeout_seconds": 5400, "phases": ["baseline", "change-impact", "generate-diff", "migrate", "old-tests", "new-tests", "rollback-test", "report"]},
                requirement_text=f"Apply the change '{change}' incrementally without regenerating unrelated code or breaking existing contracts.",
                provenance={"matrix_id": matrix["matrix_id"]},
            )
        for adv in matrix["adversarial_requirements"]:
            token = f"{stack['id']}|adversarial|{adv}"
            case_id = f"PG-ADV-{_short(token).upper()}"
            yield _base_case(
                case_id=case_id,
                title=f"Requirement reasoning with {stack['framework']}: {adv}",
                line="project-generation", family="requirement-reasoning", level="L1", priority="P0",
                source={"requirement": adv, "mode": "ambiguous-or-hostile"},
                target={"stack": stack["id"], "expected_action": "clarify-assume-safely-or-refuse"},
                capability_id=f"PG.requirements.{_slug(adv)}",
                dimensions={"stack": stack["id"], "template_or_change": _slug(adv), "deployment_or_mode": "adversarial-requirement"},
                primary_oracle="requirement-conflict-safety-and-assumption-oracle", tags=["project-generation", "requirements", "adversarial", "security"],
                execution={"adapter": "external-requirement-reasoning-harness", "timeout_seconds": 900, "hidden_tests": True},
                requirement_text=f"Detect and safely handle the requirement condition: {adv}.",
                provenance={"matrix_id": matrix["matrix_id"]},
            )


def sql_cases(root: Path) -> Iterable[dict[str, Any]]:
    matrix = _load(root / "matrices/sql-conversion.yaml")
    for pair in matrix["pairs"]:
        for feat in matrix["features"]:
            required = set(feat.get("requires_any", []))
            if required and pair["kind"] not in required:
                continue
            for variant in matrix["variants"]:
                priority = _combined_priority(pair["tier"], feat["priority"])
                token = f"{pair['id']}|{feat['id']}|{variant}"
                case_id = f"SQL-{_slug(feat['group']).upper()}-{_short(token).upper()}"
                yield _base_case(
                    case_id=case_id,
                    title=f"{pair['source']} → {pair['target']}: {feat['title']} [{variant}]",
                    line="sql-conversion", family=feat["group"], level=feat["level"], priority=priority,
                    source={"dialect": pair["source"], "database_kind": pair["kind"]},
                    target={"dialect": pair["target"], "database_kind": pair["kind"]},
                    capability_id=f"SQL.{feat['id']}",
                    dimensions={"pair": pair["id"], "feature": feat["id"], "variant": variant},
                    primary_oracle=feat["default_oracles"][0], tags=["sql", pair["kind"], variant, pair["source"], pair["target"]],
                    execution={
                        "adapter": "external-dual-database-harness", "timeout_seconds": 3600,
                        "phases": ["provision-source-target", "seed-normalized-data", "execute-source", "convert", "execute-target", "result-diff", "state-diff", "transaction-trace", "report"],
                        "fixture_selector": {"pair": pair["id"], "capability": feat["id"], "variant": variant},
                        "random_seeds": [17, 43, 101],
                    },
                    requirement_text=f"Convert {feat['title']} from {pair['source']} to {pair['target']} with equivalent results, state changes, errors, and transaction boundaries.",
                    provenance={"matrix_id": matrix["matrix_id"]},
                )


def full_product_cases(root: Path) -> Iterable[dict[str, Any]]:
    matrix = _load(root / "matrices/full-product.yaml")
    variants = matrix["variants"]
    for domain in matrix["domains"]:
        for capability in domain["capabilities"]:
            for context in domain["contexts"]:
                for variant in variants:
                    token = f"{domain['id']}|{capability['id']}|{context}|{variant['id']}"
                    case_id = f"FP-{_slug(domain['id']).upper()}-{_short(token).upper()}"
                    yield _base_case(
                        case_id=case_id,
                        title=f"{domain['title']}: {capability['title']} [{context}/{variant['id']}]",
                        line=domain["id"], family=capability["group"], level=capability["level"], priority=capability["priority"],
                        source={"domain": domain["id"], "feature": capability["id"], "context": context, "variant": variant["id"]},
                        target={"expected": "contract-correct-secure-observable-recoverable-product-behavior"},
                        capability_id=f"FP.{domain['id']}.{capability['id']}",
                        dimensions={"domain": domain["id"], "feature": capability["id"], "context": context, "variant": variant["id"]},
                        primary_oracle=capability.get("default_oracle", domain["default_oracle"]),
                        tags=["full-product", domain["id"], context, variant["id"], capability["priority"]],
                        execution={
                            "adapter": domain["adapter"], "timeout_seconds": 3600,
                            "phases": ["prepare", "seed", "execute", "observe", "negative-or-fault", "recover", "assert", "publish-evidence"],
                            "feature_selector": {"domain": domain["id"], "capability": capability["id"], "context": context, "variant": variant["id"]},
                            "random_seeds": [17, 43, 101], "hidden_tests": variant["id"] in {"negative-security", "concurrent-recovery"},
                        },
                        requirement_text=f"Verify {capability['title']} across {context} under {variant['title']} with correct authorization, state, audit, recovery, disclosure and evidence.",
                        provenance={"matrix_id": matrix["matrix_id"]},
                    )


def product_journey_cases(root: Path) -> Iterable[dict[str, Any]]:
    matrix = _load(root / "matrices/product-journeys.yaml")
    for journey in matrix["journeys"]:
        for persona in matrix["personas"]:
            for variant in matrix["variants"]:
                token = f"{journey['id']}|{persona}|{variant}"
                case_id = f"JOURNEY-{_short(token).upper()}"
                priority = journey["priority"]
                yield _base_case(
                    case_id=case_id,
                    title=f"End-to-end: {journey['title']} [{persona}/{variant}]",
                    line="product-journey", family="cross-domain-user-journey", level=journey["level"], priority=priority,
                    source={"persona": persona, "journey": journey["id"], "variant": variant},
                    target={"expected": "end-to-end-business-and-financial-consistency"},
                    capability_id=f"JOURNEY.{journey['id']}",
                    dimensions={"persona": persona, "journey": journey["id"], "variant": variant},
                    primary_oracle="end-to-end-state-security-financial-artifact-and-audit-consistency",
                    tags=["journey", "end-to-end", persona, variant],
                    execution={
                        "adapter": "external-product-journey-harness", "timeout_seconds": 7200,
                        "phases": ["provision-persona", "seed-tenant", "execute-ui-api-event-flow", "inject-variant", "reconcile", "audit", "publish-evidence"],
                        "journey": journey["id"], "persona": persona, "variant": variant, "hidden_tests": True,
                    },
                    requirement_text=f"Execute the complete product journey '{journey['title']}' as {persona} under {variant}, preserving business, security, billing, artifact and audit invariants.",
                    provenance={"matrix_id": matrix["matrix_id"]},
                )


def standards_cases(root: Path) -> Iterable[dict[str, Any]]:
    matrix = _load(root / "matrices/standards-controls.yaml")
    surfaces = ["automated-negative", "configuration-evidence", "runtime-observation"]
    for profile in matrix["profiles"]:
        for control in profile["controls"]:
            for surface in surfaces:
                token = f"{profile['id']}|{control}|{surface}"
                case_id = f"STD-{_short(token).upper()}"
                yield _base_case(
                    case_id=case_id,
                    title=f"{profile['title']}: {control} [{surface}]",
                    line="standards-assurance", family=profile["id"], level="L3", priority="P0",
                    source={"profile": profile["id"], "control": control, "source_reference": profile["source"], "surface": surface},
                    target={"expected": "testable-control-evidence-without-accreditation-claim"},
                    capability_id=f"STD.{profile['id']}.{control}",
                    dimensions={"profile": profile["id"], "control": control, "surface": surface},
                    primary_oracle="security-accessibility-supply-chain-or-observability-control-evidence",
                    tags=["standards", profile["id"], control, surface],
                    execution={
                        "adapter": "external-standards-assurance-harness", "timeout_seconds": 5400,
                        "profile": profile["id"], "control": control, "surface": surface, "hidden_tests": True,
                    },
                    requirement_text=f"Produce objective evidence for control '{control}' in profile {profile['title']} using {surface}; do not claim accreditation or legal certification.",
                    provenance={"matrix_id": matrix["matrix_id"], "source_reference": profile["source"]},
                )


def cross_cutting_cases(root: Path) -> Iterable[dict[str, Any]]:
    matrix = _load(root / "matrices/cross-cutting.yaml")
    for line in matrix["business_lines"]:
        for scenario in matrix["scenarios"]:
            for variant in matrix["variants"]:
                token = f"{line}|{scenario['id']}|{variant}"
                case_id = f"XCUT-{_short(token).upper()}"
                yield _base_case(
                    case_id=case_id,
                    title=f"{line}: {scenario['title']} [{variant}]",
                    line="cross-cutting", family="resilience-security-governance", level="L2", priority=scenario["priority"],
                    source={"business_line_under_test": line, "fault": scenario["id"], "position": variant},
                    target={"expected": "safe-fail-resume-or-rollback-with-complete-audit"},
                    capability_id=f"XCUT.{scenario['id']}",
                    dimensions={"business_line": line, "scenario": scenario["id"], "fault_position": variant},
                    primary_oracle="resilience-security-audit-invariant", tags=["cross-cutting", "fault-injection", line, variant],
                    execution={"adapter": "external-fault-injection-harness", "timeout_seconds": 3600, "fault": scenario["id"], "position": variant},
                    requirement_text=f"When '{scenario['title']}' occurs {variant}, preserve isolation, idempotency, auditability, and correct recovery semantics.",
                    provenance={"matrix_id": matrix["matrix_id"]},
                )


def smoke_cases() -> list[dict[str, Any]]:
    common = {"generated_at": GENERATED_AT, "kind": "hand-authored-smoke"}
    return [
        _base_case(
            case_id="SM-SMOKE-CONTRACT-001", title="Legacy Spring/Servlet contract equals modernized contract",
            line="spring-modernization", family="smoke", level="L1", priority="P0",
            source={"contract": "fixtures/spring-modernization/contract-equivalence/legacy-contract.json"},
            target={"contract": "fixtures/spring-modernization/contract-equivalence/modern-contract.json"},
            capability_id="SM.smoke.contract-equivalence", dimensions={"archetype": "servlet-jsp-webxml", "feature": "contract-bundle", "variant": "nominal"},
            primary_oracle="json-file-equivalence", tags=["smoke", "spring", "offline"],
            execution={"adapter": "json-file-differential", "timeout_seconds": 10, "source_path": "fixtures/spring-modernization/contract-equivalence/legacy-contract.json", "target_path": "fixtures/spring-modernization/contract-equivalence/modern-contract.json", "ignore_paths": ["$.implementation"]},
            requirement_text="Preserve route, binding, session, filter order, transaction and security contracts.", provenance=common,
        ),
        _base_case(
            case_id="XLC-SMOKE-JAVA-PY-001", title="Java to Python decimal ledger differential execution",
            line="cross-language", family="smoke", level="L1", priority="P0",
            source={"language": "java", "path": "fixtures/cross-language/java-to-python-ledger/java"},
            target={"language": "python", "path": "fixtures/cross-language/java-to-python-ledger/python"},
            capability_id="XLC.smoke.decimal-ledger", dimensions={"pair": "java-to-python", "feature": "decimal-state", "variant": "nominal"},
            primary_oracle="json-stdout-equivalence", tags=["smoke", "cross-language", "offline", "java", "python"],
            execution={"adapter": "differential-process", "timeout_seconds": 30, "source_cwd": "fixtures/cross-language/java-to-python-ledger/java", "source_command": "javac Ledger.java && java Ledger", "target_cwd": "fixtures/cross-language/java-to-python-ledger/python", "target_command": "python3 ledger.py", "output": "json"},
            requirement_text="Preserve decimal arithmetic, ordering, exception classification and final ledger state.", provenance=common,
        ),
        _base_case(
            case_id="PG-SMOKE-PY-SQLITE-001", title="Generated Python SQLite CRUD project self-tests",
            line="project-generation", family="smoke", level="L1", priority="P0",
            source={"requirement_contract": "fixtures/project-generation/python-sqlite-crud/requirements.yaml"},
            target={"stack": "python-standard-library", "path": "fixtures/project-generation/python-sqlite-crud"},
            capability_id="PG.smoke.crud-transaction-idempotency", dimensions={"stack": "python-standard-library", "template_or_change": "crud", "deployment_or_mode": "offline"},
            primary_oracle="generated-project-acceptance", tags=["smoke", "project-generation", "offline", "sqlite"],
            execution={"adapter": "local-process", "timeout_seconds": 30, "cwd": "fixtures/project-generation/python-sqlite-crud", "command": "python3 -m unittest -q"},
            requirement_text="Generate and validate a transactional, idempotent CRUD service with deterministic tests.", provenance=common,
        ),
        _base_case(
            case_id="SQL-SMOKE-SQLITE-001", title="SQL source and target query/state differential on SQLite",
            line="sql-conversion", family="smoke", level="L1", priority="P0",
            source={"dialect": "source-sqlite-compatible", "path": "fixtures/sql-conversion/sqlite-differential/source.sql"},
            target={"dialect": "target-sqlite-compatible", "path": "fixtures/sql-conversion/sqlite-differential/target.sql"},
            capability_id="SQL.smoke.query-trigger-state", dimensions={"pair": "sqlite-source-to-target", "feature": "query-trigger-state", "variant": "nominal"},
            primary_oracle="sqlite-result-and-state-equivalence", tags=["smoke", "sql", "offline", "sqlite"],
            execution={"adapter": "sqlite-differential", "timeout_seconds": 30, "seed_sql": "fixtures/sql-conversion/sqlite-differential/seed.sql", "source_sql": "fixtures/sql-conversion/sqlite-differential/source.sql", "target_sql": "fixtures/sql-conversion/sqlite-differential/target.sql", "assertion_queries": ["SELECT customer_id,total_cents FROM customer_totals ORDER BY customer_id", "SELECT event_type,customer_id,amount_cents FROM audit_log ORDER BY id", "SELECT id,customer_id,amount_cents,status FROM orders ORDER BY id"]},
            requirement_text="Preserve query results, trigger side effects and committed database state.", provenance=common,
        ),
        _base_case(
            case_id="IAM-SMOKE-POLICY-001", title="Identity tenant and RBAC policy smoke",
            line="identity-access-tenant", family="smoke", level="L1", priority="P0",
            source={"fixture": "fixtures/full-product-smokes"}, target={"expected": "tenant-safe-rbac"},
            capability_id="FP.identity-access-tenant.smoke", dimensions={"domain":"identity-access-tenant","feature":"tenant-rbac","context":"offline","variant":"nominal"},
            primary_oracle="identity-policy-security-session-and-audit", tags=["smoke","identity","offline"],
            execution={"adapter":"local-process","timeout_seconds":30,"cwd":"fixtures/full-product-smokes","command":"python3 -m unittest -q test_smoke.FullProductSmokeTests.test_identity"},
            requirement_text="Deny cross-tenant access and enforce role permission boundaries.", provenance=common,
        ),
        _base_case(
            case_id="CTRL-SMOKE-STATE-001", title="Control-plane task state and idempotency smoke",
            line="platform-control-plane", family="smoke", level="L1", priority="P0",
            source={"fixture": "fixtures/full-product-smokes"}, target={"expected": "durable-idempotent-state"},
            capability_id="FP.platform-control-plane.smoke", dimensions={"domain":"platform-control-plane","feature":"task-state","context":"offline","variant":"nominal"},
            primary_oracle="control-plane-state-idempotency-observability-and-audit", tags=["smoke","control-plane","offline"],
            execution={"adapter":"local-process","timeout_seconds":30,"cwd":"fixtures/full-product-smokes","command":"python3 -m unittest -q test_smoke.FullProductSmokeTests.test_control_plane"},
            requirement_text="Reject invalid task transitions and duplicate terminal commits.", provenance=common,
        ),
        _base_case(
            case_id="AIR-SMOKE-ROUTE-001", title="AI model router fallback and accounting smoke",
            line="ai-runtime-model-routing", family="smoke", level="L1", priority="P0",
            source={"fixture": "fixtures/full-product-smokes"}, target={"expected": "bounded-fallback"},
            capability_id="FP.ai-runtime-model-routing.smoke", dimensions={"domain":"ai-runtime-model-routing","feature":"fallback","context":"offline","variant":"nominal"},
            primary_oracle="ai-runtime-quality-cost-safety-trace-and-reproducibility", tags=["smoke","ai-runtime","offline"],
            execution={"adapter":"local-process","timeout_seconds":30,"cwd":"fixtures/full-product-smokes","command":"python3 -m unittest -q test_smoke.FullProductSmokeTests.test_model_router"},
            requirement_text="Select a healthy eligible provider, fall back once and meter exactly once.", provenance=common,
        ),
        _base_case(
            case_id="RAG-SMOKE-CITE-001", title="RAG evidence and no-answer smoke",
            line="rag-memory-knowledge", family="smoke", level="L1", priority="P0",
            source={"fixture": "fixtures/full-product-smokes"}, target={"expected": "faithful-cited-answer"},
            capability_id="FP.rag-memory-knowledge.smoke", dimensions={"domain":"rag-memory-knowledge","feature":"citation","context":"offline","variant":"nominal"},
            primary_oracle="rag-retrieval-faithfulness-citation-memory-and-security", tags=["smoke","rag","offline"],
            execution={"adapter":"local-process","timeout_seconds":30,"cwd":"fixtures/full-product-smokes","command":"python3 -m unittest -q test_smoke.FullProductSmokeTests.test_rag"},
            requirement_text="Answer only from evidence and return no-answer when evidence is absent.", provenance=common,
        ),
        _base_case(
            case_id="PI-SMOKE-EVID-001", title="Project intelligence evidence traceability smoke",
            line="project-intelligence", family="smoke", level="L1", priority="P0",
            source={"fixture": "fixtures/full-product-smokes"}, target={"expected": "evidence-linked-facts"},
            capability_id="FP.project-intelligence.smoke", dimensions={"domain":"project-intelligence","feature":"evidence-graph","context":"offline","variant":"nominal"},
            primary_oracle="project-intelligence-evidence-coverage-traceability-and-accuracy", tags=["smoke","project-intelligence","offline"],
            execution={"adapter":"local-process","timeout_seconds":30,"cwd":"fixtures/full-product-smokes","command":"python3 -m unittest -q test_smoke.FullProductSmokeTests.test_project_intelligence"},
            requirement_text="Every confirmed statement must resolve to a source file and line span.", provenance=common,
        ),
        _base_case(
            case_id="BILL-SMOKE-LEDGER-001", title="Billing reservation and usage idempotency smoke",
            line="billing-entitlements", family="smoke", level="L1", priority="P0",
            source={"fixture": "fixtures/full-product-smokes"}, target={"expected": "nonnegative-reconciled-ledger"},
            capability_id="FP.billing-entitlements.smoke", dimensions={"domain":"billing-entitlements","feature":"ledger","context":"offline","variant":"nominal"},
            primary_oracle="billing-ledger-entitlement-idempotency-and-reconciliation", tags=["smoke","billing","offline"],
            execution={"adapter":"local-process","timeout_seconds":30,"cwd":"fixtures/full-product-smokes","command":"python3 -m unittest -q test_smoke.FullProductSmokeTests.test_billing"},
            requirement_text="Reservations cannot overspend and duplicate usage cannot double charge.", provenance=common,
        ),
        _base_case(
            case_id="PAY-SMOKE-WEBHOOK-001", title="Payment webhook duplicate and out-of-order smoke",
            line="payment-finance", family="smoke", level="L1", priority="P0",
            source={"fixture": "fixtures/full-product-smokes"}, target={"expected": "one-credit-after-confirmed-payment"},
            capability_id="FP.payment-finance.smoke", dimensions={"domain":"payment-finance","feature":"webhook","context":"offline","variant":"nominal"},
            primary_oracle="payment-provider-ledger-security-idempotency-and-reconciliation", tags=["smoke","payment","offline"],
            execution={"adapter":"local-process","timeout_seconds":30,"cwd":"fixtures/full-product-smokes","command":"python3 -m unittest -q test_smoke.FullProductSmokeTests.test_payment"},
            requirement_text="Duplicate or stale callbacks cannot duplicate credit or regress terminal state.", provenance=common,
        ),
        _base_case(
            case_id="DBG-SMOKE-REPLAY-001", title="Online debug record and replay smoke",
            line="online-ide-debug", family="smoke", level="L1", priority="P0",
            source={"fixture": "fixtures/full-product-smokes"}, target={"expected": "deterministic-replay"},
            capability_id="FP.online-ide-debug.smoke", dimensions={"domain":"online-ide-debug","feature":"record-replay","context":"offline","variant":"nominal"},
            primary_oracle="ide-debug-state-causality-sandbox-and-user-content-integrity", tags=["smoke","debug","offline"],
            execution={"adapter":"local-process","timeout_seconds":30,"cwd":"fixtures/full-product-smokes","command":"python3 -m unittest -q test_smoke.FullProductSmokeTests.test_debug_replay"},
            requirement_text="Checkpoint replay reproduces state and stale fencing is rejected.", provenance=common,
        ),
    ]


def materialize(root: Path) -> dict[str, Any]:
    generators = [
        ("spring-modernization.jsonl", spring_cases),
        ("cross-language.jsonl", cross_language_cases),
        ("project-generation.jsonl", project_generation_cases),
        ("sql-conversion.jsonl", sql_cases),
        ("full-product.jsonl", full_product_cases),
        ("product-journeys.jsonl", product_journey_cases),
        ("standards-assurance.jsonl", standards_cases),
        ("cross-cutting.jsonl", cross_cutting_cases),
    ]
    counts: Counter[str] = Counter()
    priorities: Counter[str] = Counter()
    levels: Counter[str] = Counter()
    capabilities: dict[str, set[str]] = defaultdict(set)
    index_rows: list[dict[str, str]] = []
    all_ids: set[str] = set()

    for filename, generator in generators:
        path = root / "suites" / filename
        with path.open("w", encoding="utf-8") as fh:
            for case in generator(root):
                if case["id"] in all_ids:
                    raise ValueError(f"duplicate case id: {case['id']}")
                all_ids.add(case["id"])
                fh.write(json.dumps(case, ensure_ascii=False, separators=(",", ":")) + "\n")
                counts[case["business_line"]] += 1
                priorities[case["priority"]] += 1
                levels[case["level"]] += 1
                capabilities[case["business_line"]].add(case["coverage"]["capability_id"])
                index_rows.append({
                    "id": case["id"], "business_line": case["business_line"], "family": case["family"],
                    "priority": case["priority"], "level": case["level"], "profiles": ",".join(case["profiles"]),
                    "capability_id": case["coverage"]["capability_id"], "title": case["title"]
                })

    smoke_path = root / "suites/smoke.jsonl"
    with smoke_path.open("w", encoding="utf-8") as fh:
        for case in smoke_cases():
            if case["id"] in all_ids:
                raise ValueError(f"duplicate case id: {case['id']}")
            all_ids.add(case["id"])
            case["profiles"] = ["smoke", "pr", "release"]
            fh.write(json.dumps(case, ensure_ascii=False, separators=(",", ":")) + "\n")
            counts[case["business_line"]] += 1
            priorities[case["priority"]] += 1
            levels[case["level"]] += 1
            capabilities[case["business_line"]].add(case["coverage"]["capability_id"])
            index_rows.append({
                "id": case["id"], "business_line": case["business_line"], "family": case["family"],
                "priority": case["priority"], "level": case["level"], "profiles": ",".join(case["profiles"]),
                "capability_id": case["coverage"]["capability_id"], "title": case["title"]
            })

    with (root / "suites/CASE_INDEX.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["id","business_line","family","priority","level","profiles","capability_id","title"])
        writer.writeheader()
        writer.writerows(index_rows)

    summary = {
        "schema_version": "1.0", "generated_at": GENERATED_AT, "total_cases": len(all_ids),
        "by_business_line": dict(sorted(counts.items())), "by_priority": dict(sorted(priorities.items())),
        "by_level": dict(sorted(levels.items())),
        "unique_capabilities_by_business_line": {k: len(v) for k,v in sorted(capabilities.items())},
        "minimum_required": 10000, "minimum_satisfied": len(all_ids) >= 10000,
    }
    (root / "suites/summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Materialized case summary", "", f"Total concrete cases: **{summary['total_cases']:,}**", "", "## By business line", ""]
    lines += [f"- `{k}`: {v:,}" for k,v in summary["by_business_line"].items()]
    lines += ["", "## By priority", ""] + [f"- `{k}`: {v:,}" for k,v in summary["by_priority"].items()]
    lines += ["", "## Unique capability IDs", ""] + [f"- `{k}`: {v:,}" for k,v in summary["unique_capabilities_by_business_line"].items()]
    (root / "suites/summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    package_root = Path(__file__).resolve().parents[1]
    print(json.dumps(materialize(package_root), ensure_ascii=False, indent=2))
