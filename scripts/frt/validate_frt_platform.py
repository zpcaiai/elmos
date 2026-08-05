#!/usr/bin/env python3
"""Validate FRT package identity, installed interfaces, schemas, and surfaces."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = ROOT / "schemas" / "frt-g01-g30"
REQUIRED_SCHEMAS = {
    "catalog.schema.json",
    "external-evidence-record.schema.json",
    "external-evidence-trust-store.schema.json",
    "external-run-authorization.schema.json",
    "gate-request.schema.json",
    "run-completion-request.schema.json",
    "run-lease.schema.json",
    "runner-completion.schema.json",
    "skill-run-request.schema.json",
    "skill-run-result.schema.json",
}
REQUIRED_SURFACES = {
    "engines/frontend-client-engine/src/frt-contract-validation.ts",
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
    "engines/frontend-client-engine/src/vue3-react-route.ts",
    "engines/frontend-client-engine/src/frt-catalog.generated.ts",
    "engines/frontend-client-engine/src/frt-handler-registry.generated.ts",
    "engines/frontend-client-engine/src/frt-cli.ts",
    "engines/frontend-client-engine/test/frt-runtime.test.ts",
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
    "scripts/frt/refresh_frt_local_evidence.py",
    "scripts/frt/external_evidence.py",
    "scripts/frt/test_external_evidence.py",
    "scripts/frt/collect_physical_device_inventory.py",
    "scripts/batch32/run_client_gate.py",
    "client-packs/frt-g01-g30-platform/acceptance/external-evidence-profile.json",
    "client-packs/frt-g01-g30-platform/acceptance/EXTERNAL_EVIDENCE_RUNBOOK.md",
    "client-packs/frt-g01-g30-platform/acceptance/quality-matrix.json",
    "client-packs/frt-g01-g30-platform/baselines/manifest.json",
    "client-packs/frt-g01-g30-platform/visual-baselines/policy.json",
    "docs/frt-g01-g30/installed-manifest.json",
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
    installed = json.loads(
        (ROOT / "docs" / "frt-g01-g30" / "installed-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    if (
        installed.get("batch_count") != 30
        or installed.get("skill_count") != 472
        or installed.get("directed_route_count") != 30
        or installed.get("production_certification") != "NOT_CERTIFIED"
    ):
        fail("FRT installed manifest counts or evidence boundary are invalid")
    surface_count = 0
    handler_kinds: set[str] = set()
    for skill in installed.get("skills", []):
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
                "production_certification": "NOT_CERTIFIED",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
