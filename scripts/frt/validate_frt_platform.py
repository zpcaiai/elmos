#!/usr/bin/env python3
"""Validate FRT package identity, installed interfaces, schemas, and surfaces."""

from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = ROOT / "schemas" / "frt-g01-g30"
REQUIRED_SCHEMAS = {
    "catalog.schema.json",
    "external-evidence-record.schema.json",
    "external-evidence-trust-store.schema.json",
    "external-qualification-plan.schema.json",
    "external-qualification-preflight.schema.json",
    "external-qualification-local-execution.schema.json",
    "external-run-authorization.schema.json",
    "gate-request.schema.json",
    "gate-result.schema.json",
    "run-completion-request.schema.json",
    "run-lease.schema.json",
    "runner-completion.schema.json",
    "skill-execution-contract.schema.json",
    "skill-run-request.schema.json",
    "skill-run-result.schema.json",
}
REQUIRED_SURFACES = {
    "engines/frontend-client-engine/src/frt-contract-validation.ts",
    "engines/frontend-client-engine/src/frt-production-contract.ts",
    "engines/frontend-client-engine/src/frt-runtime.ts",
    "engines/frontend-client-engine/src/frt-semantic-handlers.ts",
    "engines/frontend-client-engine/src/frt-types.ts",
    "engines/frontend-client-engine/src/frt-security.ts",
    "engines/frontend-client-engine/src/frt-run-store.ts",
    "engines/frontend-client-engine/src/directional-route.ts",
    "engines/frontend-client-engine/src/frt-route-ir.ts",
    "engines/frontend-client-engine/src/frt-typed-gap-catalog.ts",
    "engines/frontend-client-engine/src/vue3-ui-ir.ts",
    "engines/frontend-client-engine/src/react-ui-ir.ts",
    "engines/frontend-client-engine/src/additional-ui-ir.ts",
    "engines/frontend-client-engine/src/frt-runnable-target.ts",
    "engines/frontend-client-engine/src/vue3-react-route.ts",
    "engines/frontend-client-engine/src/frt-catalog.generated.ts",
    "engines/frontend-client-engine/src/frt-handler-registry.generated.ts",
    "engines/frontend-client-engine/src/frt-cli.ts",
    "engines/frontend-client-engine/test/frt-runtime.test.ts",
    "engines/frontend-client-engine/test/frt-production-contract.test.ts",
    "engines/frontend-client-engine/test/frt-artifact-lifecycle.test.ts",
    "engines/frontend-client-engine/test/frt-semantic-handlers.test.ts",
    "engines/frontend-client-engine/test/vue3-ui-ir.test.ts",
    "engines/frontend-client-engine/test/react-ui-ir.test.ts",
    "engines/frontend-client-engine/test/additional-ui-ir.test.ts",
    "apps/web-console/app/frontend/FrontendTransformationStudio.tsx",
    "apps/web-console/app/frontend/FrontendTransformationStudio.module.css",
    "apps/web-console/app/lib/server/frtEngineProxy.ts",
    "apps/web-console/app/api/frt/catalog/route.ts",
    "apps/web-console/app/api/frt/runs/route.ts",
    "apps/web-console/app/api/frt/runs/[runId]/route.ts",
    "apps/web-console/app/api/frt/runs/[runId]/audit/route.ts",
    "apps/web-console/app/api/frt/runs/[runId]/[operation]/route.ts",
    "apps/web-console/e2e/frt-frontend-transformation.spec.ts",
    "apps/web-console/e2e/frt-external-quality.spec.ts",
    "apps/web-console/e2e/frt-visual-candidate.spec.ts",
    "apps/web-console/playwright.external-quality.config.ts",
    "scripts/frt/run_frt_gate.py",
    "scripts/frt/run_frt_route_toolchains.mjs",
    "schemas/frt-g01-g30/gate-result.schema.json",
    "scripts/frt/refresh_frt_local_evidence.py",
    "scripts/frt/repository_evidence.py",
    "scripts/frt/external_evidence.py",
    "scripts/frt/external_campaign_parameters.py",
    "scripts/frt/external_qualification.py",
    "scripts/frt/probe_browser_runtimes.mjs",
    "scripts/frt/test_external_evidence.py",
    "scripts/frt/test_external_campaign_parameters.py",
    "scripts/frt/test_external_qualification.py",
    "scripts/frt/collect_physical_device_inventory.py",
    "scripts/frt/record_frt_ios_device_evidence.mjs",
    "scripts/frt/test_record_frt_ios_device_evidence.py",
    "scripts/frt/materialize_frt_route.mjs",
    "scripts/frt/test_frt_route_smoke.py",
    "scripts/batch46/detect_project_profile.py",
    "scripts/batch46/scaffold_smoke_pack.py",
    "scripts/batch46/run_smoke.py",
    "scripts/batch46/validate_smoke_pack.py",
    "scripts/batch46/run_smoke_gate.py",
    "tests/batch46/test_smoke_pack.py",
    "scripts/batch32/run_client_gate.py",
    "schemas/frt-g01-g30/external-qualification-local-execution.schema.json",
    "client-packs/frt-g01-g30-platform/acceptance/external-evidence-profile.json",
    "client-packs/frt-g01-g30-platform/acceptance/external-qualification-plan.json",
    "client-packs/frt-g01-g30-platform/acceptance/EXTERNAL_EVIDENCE_RUNBOOK.md",
    "client-packs/frt-g01-g30-platform/acceptance/quality-matrix.json",
    "client-packs/frt-g01-g30-platform/baselines/manifest.json",
    "client-packs/frt-g01-g30-platform/visual-baselines/policy.json",
    "client-packs/frt-g01-g30-platform/certification/external-qualification-preflight.json",
    "client-packs/frt-g01-g30-platform/certification/external-qualification-local-execution.json",
    "docs/frt-g01-g30/installed-manifest.json",
    "docs/frt-g01-g30/compiled-skill-contracts.json",
}
SURFACE_NAMES = {
    "contract",
    "runtime",
    "control_plane",
    "web_console",
    "admin_console",
    "tests",
}
EXPECTED_HANDLER_KINDS = {
    "governance",
    "estate_discovery",
    "semantic_ir",
    "typed_contract",
    "migration_planning",
    "source_generation",
    "build_toolchain",
    "test_automation",
    "delivery_pipeline",
    "design_system",
    "mobile_client",
    "cross_platform",
    "directional_route",
    "route_orchestration",
    "compatibility",
    "advanced_verification",
    "runtime_operations",
    "product_workflow",
    "administration",
    "performance_capacity",
    "resilience_dr",
    "security_privacy",
    "production_readiness",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> int:
    subprocess.run(
        [sys.executable, str(ROOT / "tooling" / "integrate_frt_g01_g30.py"), "--check"],
        cwd=ROOT,
        check=True,
    )
    schema_files = {path.name for path in SCHEMA_ROOT.glob("*.json")}
    if schema_files != REQUIRED_SCHEMAS:
        fail(f"FRT schema inventory mismatch: {sorted(schema_files)}")
    for path in sorted(SCHEMA_ROOT.glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            fail(f"FRT schema does not use JSON Schema 2020-12: {path}")
        if not schema.get("$id") or schema.get("type") != "object":
            fail(f"FRT schema identity or root type is invalid: {path}")
    for relative in REQUIRED_SURFACES:
        if not (ROOT / relative).is_file():
            fail(f"FRT integration surface is missing: {relative}")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "frt" / "repository_evidence.py"),
            "check",
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "frt" / "external_qualification.py"),
            "check",
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "frt" / "external_qualification.py"),
            "check-preflight",
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "frt" / "external_qualification.py"),
            "check-execution",
        ],
        cwd=ROOT,
        check=True,
    )
    qualification_plan_path = (
        ROOT / "client-packs/frt-g01-g30-platform/acceptance/external-qualification-plan.json"
    )
    qualification_preflight_path = (
        ROOT / "client-packs/frt-g01-g30-platform/certification/external-qualification-preflight.json"
    )
    qualification_execution_path = (
        ROOT / "client-packs/frt-g01-g30-platform/certification/external-qualification-local-execution.json"
    )
    qualification_plan = json.loads(qualification_plan_path.read_text(encoding="utf-8"))
    qualification_preflight = json.loads(
        qualification_preflight_path.read_text(encoding="utf-8")
    )
    qualification_execution = json.loads(
        qualification_execution_path.read_text(encoding="utf-8")
    )
    canonical_plan_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            qualification_plan,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    qualification_cases = qualification_preflight.get("cases")
    if (
        qualification_plan.get("case_count") != 15
        or qualification_preflight.get("case_count") != 15
        or qualification_preflight.get("plan_sha256") != canonical_plan_digest
        or not isinstance(qualification_cases, list)
        or len(qualification_cases) != 15
        or any(case.get("external_state") != "NOT_RUN" for case in qualification_cases)
        or any(case.get("production_operation_authorized") is not False for case in qualification_cases)
        or qualification_preflight.get("external_state_counts") != {"NOT_RUN": 15}
        or qualification_preflight.get("production_operation_authorized") is not False
        or qualification_preflight.get("production_certification") != "NOT_CERTIFIED"
    ):
        fail("FRT external qualification plan or preflight boundary is invalid")
    execution_cases = qualification_execution.get("cases")
    execution_counts = qualification_execution.get("local_execution_counts")
    if (
        qualification_execution.get("case_count") != 15
        or qualification_execution.get("plan_sha256") != canonical_plan_digest
        or qualification_execution.get("preflight_sha256")
        != "sha256:" + hashlib.sha256(qualification_preflight_path.read_bytes()).hexdigest()
        or qualification_execution.get("code_contract_counts")
        != {"PASSED_LOCAL_TOOLING": 15}
        or not isinstance(execution_counts, dict)
        or set(execution_counts) - {
            "BLOCKED_TOOLCHAIN",
            "READY_FOR_LOCAL_EXECUTION",
            "REQUIRES_EXTERNAL_AUTHORITY",
        }
        or execution_counts.get("REQUIRES_EXTERNAL_AUTHORITY") != 11
        or execution_counts.get("BLOCKED_TOOLCHAIN", 0)
        + execution_counts.get("READY_FOR_LOCAL_EXECUTION", 0)
        != 4
        or not isinstance(execution_cases, list)
        or len(execution_cases) != 15
        or any(case.get("code_contract_state") != "PASSED_LOCAL_TOOLING" for case in execution_cases)
        or any(case.get("external_state") != "NOT_RUN" for case in execution_cases)
        or any(case.get("production_operation_authorized") is not False for case in execution_cases)
        or any(case.get("certification") != "NOT_CERTIFIED" for case in execution_cases)
        or qualification_execution.get("external_state_counts") != {"NOT_RUN": 15}
        or qualification_execution.get("production_operation_authorized") is not False
        or qualification_execution.get("production_certification") != "NOT_CERTIFIED"
    ):
        fail("FRT local adapter execution report or evidence boundary is invalid")
    installed = json.loads(
        (ROOT / "docs" / "frt-g01-g30" / "installed-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    if (
        installed.get("batch_count") != 30
        or installed.get("skill_count") != 472
        or installed.get("directed_route_count") != 30
        or installed.get("production_operation_authorized") is not False
        or installed.get("production_certification") != "NOT_CERTIFIED"
    ):
        fail("FRT installed manifest counts or evidence boundary are invalid")
    compiled = json.loads(
        (ROOT / "docs" / "frt-g01-g30" / "compiled-skill-contracts.json").read_text(
            encoding="utf-8"
        )
    )
    contracts = compiled.get("contracts")
    if (
        compiled.get("schemaVersion") != "1.0"
        or compiled.get("skillCount") != 472
        or compiled.get("productionOperationAuthorized") is not False
        or compiled.get("productionCertification") != "NOT_CERTIFIED"
        or not isinstance(contracts, list)
        or len(contracts) != 472
    ):
        fail("FRT compiled execution contract inventory is invalid")
    contract_by_id: dict[str, dict] = {}
    capabilities: set[str] = set()
    contract_digests: set[str] = set()
    for contract in contracts:
        skill_id = contract.get("skillId")
        capability = contract.get("capabilityKey")
        contract_digest = contract.get("contractDigest")
        unsigned_contract = {
            key: value for key, value in contract.items() if key != "contractDigest"
        }
        computed_contract_digest = "sha256:" + hashlib.sha256(
            json.dumps(
                unsigned_contract,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        input_contract = contract.get("inputContract")
        if (
            not isinstance(skill_id, str)
            or skill_id in contract_by_id
            or not isinstance(capability, str)
            or not capability.startswith(f"frt.{str(contract.get('batch', '')).lower()}.")
            or capability in capabilities
            or not isinstance(contract_digest, str)
            or len(contract_digest) != 71
            or not contract_digest.startswith("sha256:")
            or contract_digest in contract_digests
            or contract_digest != computed_contract_digest
            or not isinstance(input_contract, dict)
            or input_contract.get("additionalProperties") is not False
            or not isinstance(input_contract.get("required"), list)
            or not isinstance(input_contract.get("optional"), list)
            or len(contract.get("outputContracts", [])) != 4
            or len(contract.get("apiOperations", [])) != 5
            or len(contract.get("requiredSurfaces", [])) != 6
            or contract.get("assuranceCounts", {}).get("surfaceCount") != 6
            or contract.get("productionOperationAuthority") != "EXTERNAL_ONLY"
            or contract.get("certification") != "NOT_CERTIFIED"
        ):
            fail(f"FRT compiled execution contract is invalid: {skill_id}")
        contract_by_id[skill_id] = contract
        capabilities.add(capability)
        contract_digests.add(contract_digest)
    surface_count = 0
    handler_kinds: set[str] = set()
    for skill in installed.get("skills", []):
        contract = contract_by_id.get(skill.get("skill_id"))
        if (
            contract is None
            or skill.get("capability_key") != contract.get("capabilityKey")
            or skill.get("execution_class") != contract.get("executionClass")
            or skill.get("execution_contract_sha256") != contract.get("contractDigest")
            or skill.get("source_sha256") != contract.get("sourceSha256")
        ):
            fail(f"FRT installed execution contract binding is invalid: {skill.get('skill_id')}")
        surfaces = skill.get("surface_manifests")
        if not isinstance(surfaces, dict) or set(surfaces) != SURFACE_NAMES:
            fail(f"FRT Skill surface inventory is incomplete: {skill.get('skill_id')}")
        handler_kind = skill.get("handler_kind")
        if not isinstance(handler_kind, str) or not handler_kind:
            fail(f"FRT Skill handler kind is missing: {skill.get('skill_id')}")
        handler_kinds.add(handler_kind)
        for surface_name, reference in surfaces.items():
            path = ROOT / str(reference.get("path", ""))
            if not path.is_file():
                fail(f"FRT surface manifest is missing: {skill.get('skill_id')}: {surface_name}")
            surface = json.loads(path.read_text(encoding="utf-8"))
            if (
                surface.get("skill_id") != skill.get("skill_id")
                or surface.get("surface") != surface_name
                or surface.get("status") != "shared_implementation"
                or surface.get("handler_kind") != handler_kind
                or surface.get("capability_key") != contract.get("capabilityKey")
                or surface.get("execution_class") != contract.get("executionClass")
                or surface.get("execution_contract_sha256") != contract.get("contractDigest")
                or surface.get("input_contract") != contract.get("inputContract")
                or not surface.get("implementation_paths")
            ):
                fail(f"FRT surface manifest is invalid: {skill.get('skill_id')}: {surface_name}")
            surface_count += 1
    if surface_count != 472 * 6:
        fail(f"FRT surface manifest count is invalid: {surface_count}")
    if handler_kinds != EXPECTED_HANDLER_KINDS:
        fail(f"FRT handler kind inventory is invalid: {sorted(handler_kinds)}")
    runtime_source = (
        ROOT / "engines/frontend-client-engine/src/frt-runtime.ts"
    ).read_text(encoding="utf-8")
    if 'semanticAnalysis:' in runtime_source or 'externalExecution: "NOT_RUN"' in runtime_source:
        fail("FRT runtime still contains the legacy metadata-only semantic fallback")
    print(
        json.dumps(
            {
                "status": "PASSED",
                "batches": 30,
                "skills": 472,
                "directed_routes": 30,
                "schemas": len(REQUIRED_SCHEMAS),
                "shared_surfaces": len(REQUIRED_SURFACES),
                "skill_surface_manifests": surface_count,
                "handler_kinds": len(handler_kinds),
                "compiled_execution_contracts": len(contract_by_id),
                "production_operation_authorized": False,
                "production_certification": "NOT_CERTIFIED",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
