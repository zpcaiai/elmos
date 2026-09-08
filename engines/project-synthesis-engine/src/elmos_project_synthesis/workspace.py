from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from importlib.resources import files as package_files
from pathlib import Path, PurePosixPath
from typing import Any, cast

from .deployment_guidance import render_deployment_guidance
from .dotnet_target import render_dotnet
from .go_target import render_go
from .insights import render_generation_insights, render_insights_markdown
from .java_target import render_java
from .kotlin_target import render_kotlin
from .models import (
    TARGET_PROFILES,
    SynthesisRequest,
    p0_request_blockers,
    p0_scope_payload,
    request_payload,
    sha256_json,
)
from .php_target import render_php
from .production_profile import render_production_assets
from .project_documentation import (
    DOCUMENT_SOURCE_REFS,
    DOCUMENTATION_STATUS,
    render_project_documentation,
)
from .project_graphs import (
    DEPENDENCY_GRAPH_PATH,
    PROJECT_STRUCTURE_PATH,
    render_declared_dependency_graph,
    render_project_structure,
)
from .python_target import render_python
from .rendering import clean, pretty_json
from .rust_target import render_rust
from .supply_chain import SBOM_PATH, build_dependency_sbom, canonical_json, sbom_status, sha256_bytes
from .typescript_target import render_typescript

ENGINE_VERSION = "1.4.0"
COMPATIBLE_MANIFEST_VERSIONS = frozenset({"1.2.0", "1.3.0", ENGINE_VERSION})

_COMPOSE_LIMITS: dict[str, tuple[str, str]] = {
    "java": ("1.0", "1g"),
    "python": ("1.0", "768m"),
    "csharp": ("1.0", "1g"),
    "typescript": ("1.0", "768m"),
    "go": ("0.5", "256m"),
    "kotlin": ("1.5", "1536m"),
    "php": ("0.5", "256m"),
    "rust": ("0.5", "256m"),
}


class WorkspaceConflictError(RuntimeError):
    """Raised when generation would overwrite unowned or modified content."""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_path(root: Path, relative: str) -> Path:
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise WorkspaceConflictError(f"UNSAFE_GENERATED_PATH:{relative}")
    target = root.joinpath(*candidate.parts)
    resolved_parent = target.parent.resolve(strict=False)
    if root.resolve(strict=False) not in (resolved_parent, *resolved_parent.parents):
        raise WorkspaceConflictError(f"GENERATED_PATH_ESCAPE:{relative}")
    return target


def _target_directory(language: str) -> str:
    return str(TARGET_PROFILES[language]["directory"])


def _render_psir(request: SynthesisRequest) -> dict[str, Any]:
    payload = request_payload(request.raw)
    return {
        "schema_version": "1.1.0",
        "project": payload["project"],
        "entities": payload["entities"],
        "relations": payload["relations"],
        "business_rules": payload["business_rules"],
        "permissions": payload["permissions"],
        "requirements": payload["requirements"],
        "acceptance_criteria": payload["acceptance_criteria"],
        "actors": payload.get("actors", []),
        "constraints": payload.get("constraints", []),
        "assumptions": payload.get("assumptions", []),
        "quality_attributes": payload.get("quality_attributes", []),
        "open_questions": payload.get("open_questions", []),
    }


def _render_blueprint(request: SynthesisRequest) -> dict[str, Any]:
    approval_hash = str(request.raw["approval"]["approved_payload_sha256"])
    applications = [
        {
            "id": f"APP-{target.language.upper()}",
            "language": target.language,
            "profile": f"{target.framework}-{target.runtime}",
            "port": target.port,
            "storage": request.persistence,
            "auth_mode": request.auth_mode,
            "toolchain": TARGET_PROFILES[target.language]["toolchain"],
        }
        for target in request.targets
    ]
    return {
        "schema_version": "1.1.0",
        "project": {
            "id": request.raw["project"]["id"],
            "name": request.project_name,
            "requirements_baseline_ref": f"sha256:{approval_hash}",
            "architecture_baseline_ref": f"sha256:{sha256_json(applications)}",
        },
        "applications": applications,
        "repository": {
            "mode": "polyglot-monorepo",
            "generated_areas": [_target_directory(target.language) for target in request.targets],
        },
        "runtime": {target.language: target.runtime for target in request.targets},
        "dependencies": [
            {
                "target": target.language,
                "catalog": f"{target.framework}-{target.runtime}",
                "source_skill": TARGET_PROFILES[target.language]["source_skill"],
            }
            for target in request.targets
        ],
        "build": {"reproducible_intent": True, "external_dependency_resolution_evidence": "NOT_RUN"},
        "configuration": [
            {"key": "APP_NAME", "secret": False},
            {"key": "APP_ENV", "secret": False},
            {"key": "PORT", "secret": False},
            {"key": "LOG_LEVEL", "secret": False},
            *(
                [{"key": "ELMOS_DATABASE_URL_FILE", "secret": True, "transport": "file-reference"}]
                if request.requires_database
                else []
            ),
            *(
                [
                    {"key": "ELMOS_AUTH_ISSUER", "secret": False},
                    {"key": "ELMOS_AUTH_AUDIENCE", "secret": False},
                    {"key": "ELMOS_JWT_HMAC_SECRET_FILE", "secret": True, "transport": "file-reference"},
                ]
                if request.auth_mode == "jwt"
                else []
            ),
            *(
                [
                    {"key": "ELMOS_AUTH_ISSUER", "secret": False},
                    {"key": "ELMOS_AUTH_AUDIENCE", "secret": False},
                    {"key": "ELMOS_OIDC_JWKS_FILE", "secret": True, "transport": "file-reference"},
                ]
                if request.auth_mode == "oidc"
                else []
            ),
        ],
        "quality": {"unit_tests": True, "lint": True, "type_check": True, "startup_probe": True},
        "generation_units": [
            {
                "id": f"GEN-{target.language.upper()}",
                "kind": "project",
                "target_path": _target_directory(target.language),
                "ownership": "managed",
                "source_refs": [
                    *[f"REQ-CRUD-{index:03d}" for index in range(1, len(request.entities) + 1)],
                    "REQ-HEALTH-001",
                    "REQ-DELIVERY-001",
                ],
            }
            for target in request.targets
        ],
    }


def _render_asset_graph(request: SynthesisRequest) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {
            "id": "approved-request",
            "kind": "requirement-baseline",
            "path": "requirements/approved-request.json",
            "status": "APPROVED",
            "sha256": request.request_hash,
        },
        {
            "id": "psir",
            "kind": "typed-ir",
            "path": "requirements/psir.json",
            "status": "GENERATED",
        },
        {
            "id": "project-blueprint",
            "kind": "architecture-blueprint",
            "path": "requirements/project-blueprint.json",
            "status": "GENERATED",
        },
        {
            "id": "architecture-document",
            "kind": "architecture-document",
            "path": "docs/ARCHITECTURE.md",
            "status": DOCUMENTATION_STATUS,
        },
        {
            "id": "database-design-document",
            "kind": "database-design-document",
            "path": "docs/DATABASE_DESIGN.md",
            "status": DOCUMENTATION_STATUS,
        },
        {
            "id": "migration-guide",
            "kind": "migration-document",
            "path": "docs/MIGRATION_GUIDE.md",
            "status": DOCUMENTATION_STATUS,
        },
        {
            "id": "change-history",
            "kind": "change-impact-document",
            "path": "docs/CHANGE_HISTORY.md",
            "status": DOCUMENTATION_STATUS,
        },
        {
            "id": "project-insights-document",
            "kind": "project-insights-document",
            "path": "docs/PROJECT_INSIGHTS.md",
            "status": DOCUMENTATION_STATUS,
        },
    ]
    edges: list[dict[str, str]] = [
        {"from": "approved-request", "to": "psir", "relation": "normalizes-to"},
        {"from": "psir", "to": "project-blueprint", "relation": "plans"},
        {"from": "project-blueprint", "to": "architecture-document", "relation": "documents"},
        {"from": "project-blueprint", "to": "database-design-document", "relation": "documents-data"},
        {"from": "database-design-document", "to": "migration-guide", "relation": "governs-migration"},
        {"from": "approved-request", "to": "change-history", "relation": "records-impact"},
        {
            "from": "project-blueprint",
            "to": "project-insights-document",
            "relation": "summarizes-evidence",
        },
    ]
    for target in request.targets:
        source_id = f"{target.language}-source"
        evidence_id = f"{target.language}-verification"
        nodes.extend(
            [
                {
                    "id": source_id,
                    "kind": "generated-project",
                    "path": _target_directory(target.language),
                    "status": "GENERATED",
                    "source_skill": TARGET_PROFILES[target.language]["source_skill"],
                },
                {
                    "id": evidence_id,
                    "kind": "verification-evidence",
                    "path": f".elmos/verification/{target.language}.json",
                    "status": "NOT_RUN",
                },
            ]
        )
        edges.extend(
            [
                {"from": "project-blueprint", "to": source_id, "relation": "emits"},
                {"from": source_id, "to": evidence_id, "relation": "requires-verification"},
            ]
        )
    return {
        "schema_version": "1.0.0",
        "graph_kind": "project-synthesis-asset-graph",
        "nodes": nodes,
        "edges": edges,
        "external_evidence_status": "NOT_RUN",
    }


def _render_build_graph(request: SynthesisRequest) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {
            "id": "approved-request",
            "kind": "approval",
            "status": "APPROVED",
        }
    ]
    edges: list[dict[str, str]] = []
    for target in request.targets:
        profile = TARGET_PROFILES[target.language]
        phases = (
            ("generate", "generation", "GENERATED"),
            ("build", "native-build", "NOT_RUN"),
            ("test", "native-test", "NOT_RUN"),
            ("startup", "startup-probe", "NOT_RUN"),
        )
        previous = "approved-request"
        for phase, kind, status in phases:
            node_id = f"{target.language}-{phase}"
            node: dict[str, Any] = {
                "id": node_id,
                "language": target.language,
                "kind": kind,
                "status": status,
            }
            if phase != "generate":
                node["required_runtime"] = target.runtime
                node["required_framework"] = target.framework
                node["required_toolchain"] = profile["toolchain"]
            else:
                node["source_skill"] = profile["source_skill"]
            nodes.append(node)
            edges.append({"from": previous, "to": node_id, "relation": "must-complete-before"})
            previous = node_id
    return {
        "schema_version": "1.0.0",
        "graph_kind": "polyglot-build-graph",
        "execution_policy": {
            "independent_targets": True,
            "fail_closed_on_missing_toolchain": True,
            "generated_is_not_verified": True,
        },
        "nodes": nodes,
        "edges": edges,
        "external_execution_status": "NOT_RUN",
    }


def _compose(request: SynthesisRequest) -> str:
    blocks: list[str] = [f"name: {request.project_name}", "services:"]
    for target in request.targets:
        directory = _target_directory(target.language)
        cpus, memory = _COMPOSE_LIMITS[target.language]
        blocks.extend(
            [
                f"  {target.language}:",
                "    build:",
                f"      context: ./{directory}",
                "      dockerfile: Dockerfile",
                "    environment:",
                f"      APP_NAME: {request.project_name}",
                "      APP_ENV: development",
                f'      PORT: "{target.port}"',
                f'    ports: ["127.0.0.1:{target.port}:{target.port}"]',
                "    init: true",
                "    read_only: true",
                '    tmpfs: ["/tmp:rw,noexec,nosuid,nodev,size=64m"]',
                "    cap_drop: [ALL]",
                "    security_opt: [no-new-privileges:true]",
                "    pids_limit: 256",
                f"    cpus: \"{cpus}\"",
                f"    mem_limit: {memory}",
                "    stop_grace_period: 15s",
                "    networks: [runtime]",
                "    labels:",
                "      io.elmos.generated: \"true\"",
                "      io.elmos.runtime-scope: local-development",
            ]
        )
    blocks.extend(["networks:", "  runtime:", "    internal: true"])
    return "\n".join(blocks) + "\n"


def _root_makefile(request: SynthesisRequest) -> str:
    first = request.targets[0].language
    phony_targets = " ".join(
        [
            "doctor",
            "verify",
            "run",
            "plan",
            "up",
            "down",
            "status",
            "smoke",
            *[f"run-{target.language}" for target in request.targets],
            *[f"verify-{target.language}" for target in request.targets],
        ]
    )
    lines = [
        f".PHONY: {phony_targets}",
        "",
        "doctor:",
        f"\tpython3 scripts/projectctl.py doctor --target {first}",
        "",
        "verify:",
        "\tpython3 scripts/projectctl.py verify --all",
        "",
        f"run: run-{first}",
        "",
        "plan:",
        "\tpython3 scripts/projectctl.py plan",
        "",
        "up:",
        "\tpython3 scripts/projectctl.py up --timeout 180",
        "",
        "down:",
        "\tpython3 scripts/projectctl.py down",
        "",
        "status:",
        "\tpython3 scripts/projectctl.py status",
        "",
        "smoke:",
        "\tpython3 scripts/projectctl.py smoke --requests 5 --evidence .elmos/local-smoke.json",
    ]
    for target in request.targets:
        lines.extend(
            [
                "",
                f"run-{target.language}:",
                f"\tpython3 scripts/projectctl.py run --target {target.language}",
                "",
                f"verify-{target.language}:",
                f"\tpython3 scripts/projectctl.py verify --target {target.language}",
            ]
        )
    return "\n".join(lines) + "\n"


def _performance_budget(request: SynthesisRequest) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.project-performance-budget",
        "status": "DEFINED_NOT_EVIDENCED",
        "local_health_smoke": {
            "requests_per_target": 5,
            "p95_latency_ms": 500,
            "error_count": 0,
            "runner": "scripts/projectctl.py smoke",
        },
        "application_slo": {
            "p95_latency_ms": 300,
            "availability": 0.999,
            "evidence": "NOT_RUN",
            "note": "Requires representative authenticated business traffic; health probes are not a substitute.",
        },
        "local_container_limits": {
            target.language: {
                "cpus": _COMPOSE_LIMITS[target.language][0],
                "memory": _COMPOSE_LIMITS[target.language][1],
                "pids": 256,
            }
            for target in request.targets
        },
        "production_capacity_evidence": "NOT_RUN",
        "external_cost_evidence": "NOT_RUN",
    }


def _root_readme(request: SynthesisRequest) -> str:
    target_rows = "\n".join(
        (
            f"| {target.language} | {target.framework} {target.runtime} | "
            f"`{_target_directory(target.language)}/` | {target.port} |"
        )
        for target in request.targets
    )
    build_commands = []
    if any(target.language == "java" for target in request.targets):
        build_commands.append("(cd java && mvn -B test)")
    if any(target.language == "python" for target in request.targets):
        build_commands.append(
            "(cd python && uv lock && uv sync --locked --python 3.12 && uv run pytest "
            "&& uv run ruff check src tests && uv run mypy src)"
        )
    if any(target.language == "csharp" for target in request.targets):
        build_commands.append(
            "(cd dotnet && dotnet restore --use-lock-file && dotnet restore --locked-mode && dotnet test)"
        )
    if any(target.language == "typescript" for target in request.targets):
        build_commands.append(
            "(cd typescript && pnpm install --lockfile-only && pnpm install --frozen-lockfile "
            "&& pnpm check && pnpm test && pnpm build)"
        )
    if any(target.language == "go" for target in request.targets):
        build_commands.append("(cd go && go vet ./... && go test -race ./... && go build ./...)")
    if any(target.language == "kotlin" for target in request.targets):
        build_commands.append("(cd kotlin && gradle --no-daemon --write-locks test build)")
    if any(target.language == "php" for target in request.targets):
        build_commands.append("(cd php && php -l src/Store.php && php tests/run.php)")
    if any(target.language == "rust" for target in request.targets):
        build_commands.append(
            "(cd rust && cargo generate-lockfile && cargo fmt --check "
            "&& cargo clippy --locked --all-targets --all-features -- -D warnings "
            "&& cargo test --locked --all-features)"
        )
    commands = "\n".join(build_commands)
    return clean(
        f"""
        # {request.project_name}

        {request.description}

        This workspace was generated from an approved, hash-bound ELMOS Project Synthesis
        requirement baseline. Generators did not consume raw conversation text directly.

        | Target | Profile | Directory | Port |
        |---|---|---|---:|
        {target_rows}

        ## Verify

        ```bash
        {commands}
        ```

        Or run `elmos-project-synthesis verify --workspace .` from the engine environment.

        ## One-command local operation

        ```bash
        make doctor       # verify managed-file integrity and local prerequisites
        make run          # run the first generated target with its exact native harness
        make up           # hardened loopback-only Compose path for in-memory/no-auth starters
        make smoke        # exact service-identity health probe and bounded local latency evidence
        make down         # stop the Compose stack and remove orphan containers
        ```

        Every selected target also has `make run-<language>` and `make verify-<language>`.
        PostgreSQL/JWT/OIDC profiles intentionally use `make run-<language>` because that
        target-owned harness provisions disposable PostgreSQL, ephemeral local identity
        material, migrations, tenant-isolation checks and cleanup. The simpler Compose
        development path refuses those profiles instead of starting a misleading partial stack.

        ## Generated contracts

        - `requirements/approved-request.json`: immutable approved input.
        - `requirements/psir.json`: normalized Project Synthesis IR.
        - `requirements/project-blueprint.json`: selected language/runtime/build profiles.
        - `requirements/asset-graph.json`: generated assets and missing evidence links.
        - `requirements/build-graph.json`: per-target generate/build/test/startup dependencies.
        - `requirements/project-insights.json`: structure, semantic mapping, behavior, and pairwise evidence state.
        - `requirements/source-provenance.json`: imported file, URL, Skill, and description digests.
        - `docs/PROJECT_INSIGHTS.md`: Mermaid structure graph and explicit equivalence matrices.
        - `docs/ARCHITECTURE.md`: architecture baseline, boundaries, targets, decisions, and review status.
        - `docs/DATABASE_DESIGN.md`: logical/physical data model, relations, constraints, indexes, and RLS.
        - `docs/MIGRATION_GUIDE.md`: upgrade, data migration, verification, rollback, and evidence plan.
        - `docs/CHANGE_HISTORY.md`: baseline history and behavior/API/data/security/operations impact.
        - `docs/LOCAL_RUN.md`: exact local hardware, toolchain, verification and startup steps.
        - `docs/CLOUD_DEPLOYMENT.md`: cloud options and the recommended Cloud Run configuration.
        - `scripts/projectctl.py`: integrity-bound local doctor, verify, run, Compose and smoke controller.
        - `operations/performance-budget.json`: local health and external business-load budgets.
        - `deploy/deployment-options.json`: fail-closed, machine-readable deployment handoff.
        - `deploy/cloud-run-control.py`: plan-first Cloud Run deploy, health, rollback, and cleanup controller.
        - `deploy/cloud-run-request.example.json`: private-ingress, digest-pinned deployment request template.
        - `deploy/cloud-run-authorization.example.json`: fail-closed exact-scope authorization template.
        - `requirements/dependency-sbom.cdx.json`: CycloneDX dependency inventory with per-target
          transitive-resolution completeness; missing native lock evidence stays explicit.
        - `.elmos/generation-manifest.json`: ownership, hashes, P0 scope, supply-chain links, and claim boundary.

        ## Current boundary

        The selected persistence profile is `{request.persistence}` and authentication profile is
        `{request.auth_mode}`. Provider integration, production data migration, tenant enforcement,
        and external recovery remain separate gates. Local generation is `GENERATED`; production delivery and all
        external certification remain `NOT_RUN`.
        """
    )


def render_workspace(request: SynthesisRequest) -> dict[str, str]:
    files: dict[str, str] = {
        "README.md": _root_readme(request),
        "Makefile": _root_makefile(request),
        "docker-compose.yml": _compose(request),
        "scripts/projectctl.py": package_files("elmos_project_synthesis")
        .joinpath("local_project_control.py")
        .read_text(encoding="utf-8"),
        "operations/performance-budget.json": pretty_json(_performance_budget(request)),
        "requirements/approved-request.json": pretty_json(request.raw),
        "requirements/psir.json": pretty_json(_render_psir(request)),
        "requirements/project-blueprint.json": pretty_json(_render_blueprint(request)),
        "requirements/asset-graph.json": pretty_json(_render_asset_graph(request)),
        "requirements/build-graph.json": pretty_json(_render_build_graph(request)),
        "requirements/source-provenance.json": pretty_json(
            {
                "schema_version": "1.0.0",
                "kind": "elmos.requirement-source-provenance",
                "status": "HASH_BOUND" if request.requirement_sources else "DIRECT_DESCRIPTION",
                "source_bundle_sha256": request.source_bundle_sha256,
                "description_sha256": _sha256_text(request.description),
                "sources": list(request.requirement_sources),
                "warnings": sorted(
                    {
                        warning
                        for source in request.requirement_sources
                        for warning in source.get("warnings", [])
                        if isinstance(warning, str)
                    }
                ),
                "execution_boundary": (
                    "Imported Skills and documents were treated as untrusted requirements; "
                    "their instructions were not executed during source ingestion."
                ),
            }
        ),
        "docs/traceability.md": clean(
            """
            # Requirement traceability

            | Requirement | Generated verification |
            |---|---|
            | REQ-CRUD-001 | Target API tests create and list the primary entity. |
            | REQ-HEALTH-001 | Target API tests and startup probes call `GET /health`. |
            | REQ-DELIVERY-001 | Build, test, configuration, CI, container, Kubernetes, OpenAPI, and evidence assets. |

            Missing production identity, persistence, image-digest, deployment, SLO, restore,
            and external gate evidence remains explicit and cannot be inferred from this table.
            """
        ),
    }
    for path, content in render_project_documentation(request).items():
        if path in files:
            raise WorkspaceConflictError(f"DUPLICATE_GENERATED_PATH:{path}")
        files[path] = content
    for target in request.targets:
        rendered = {
            "java": render_java,
            "python": render_python,
            "csharp": render_dotnet,
            "typescript": render_typescript,
            "go": render_go,
            "kotlin": render_kotlin,
            "php": render_php,
            "rust": render_rust,
        }[target.language](request, target.port)
        prefix = _target_directory(target.language)
        for relative, content in rendered.items():
            if request.requires_database and relative == "deploy/kubernetes.yaml":
                path = relative if len(request.targets) == 1 else f"deploy/{target.language}-kubernetes.yaml"
            else:
                path = f"{prefix}/{relative}"
            if path in files:
                raise WorkspaceConflictError(f"DUPLICATE_GENERATED_PATH:{path}")
            files[path] = content
            if relative == ".github/workflows/ci.yml":
                root_workflow = f".github/workflows/{target.language}-ci.yml"
                monorepo_content = content
                if "        defaults:\n" not in monorepo_content:
                    monorepo_content = monorepo_content.replace(
                        "        runs-on: ubuntu-latest\n",
                        "        runs-on: ubuntu-latest\n"
                        "        defaults:\n"
                        "          run:\n"
                        f"            working-directory: {prefix}\n",
                        1,
                    )
                files[root_workflow] = monorepo_content
    for path, content in render_production_assets(request).items():
        if path in files:
            raise WorkspaceConflictError(f"DUPLICATE_GENERATED_PATH:{path}")
        files[path] = content
    for path, content in render_deployment_guidance(request).items():
        if path in files:
            raise WorkspaceConflictError(f"DUPLICATE_GENERATED_PATH:{path}")
        files[path] = content

    dependency_sbom = build_dependency_sbom(request, files)
    files[SBOM_PATH] = pretty_json(dependency_sbom)

    insight_path = "requirements/project-insights.json"
    insight_report_path = "docs/PROJECT_INSIGHTS.md"
    managed_paths = [
        *files,
        PROJECT_STRUCTURE_PATH,
        DEPENDENCY_GRAPH_PATH,
        insight_path,
        insight_report_path,
    ]
    project_structure = render_project_structure(request, managed_paths)
    declared_dependencies = render_declared_dependency_graph(request)
    project_insights = render_generation_insights(
        request,
        project_structure=project_structure,
        declared_dependencies=declared_dependencies,
    )
    files[PROJECT_STRUCTURE_PATH] = pretty_json(project_structure)
    files[DEPENDENCY_GRAPH_PATH] = pretty_json(declared_dependencies)
    files[insight_path] = pretty_json(project_insights)
    files[insight_report_path] = render_insights_markdown(request, project_insights)

    manifest_entries = [
        {
            "path": path,
            "sha256": _sha256_text(content),
            "ownership": "managed",
            "source_refs": list(DOCUMENT_SOURCE_REFS.get(path, ("approved-request", "PG001-PG417"))),
        }
        for path, content in sorted(files.items())
    ]
    manifest_entry_by_path = {entry["path"]: entry for entry in manifest_entries}
    p0_scope = p0_scope_payload()
    p0_blockers = p0_request_blockers(request)
    manifest = {
        "schema_version": "1.2.0",
        "engine": "elmos.project-synthesis",
        "engine_version": ENGINE_VERSION,
        "request_sha256": request.request_hash,
        "approved_payload_sha256": request.raw["approval"]["approved_payload_sha256"],
        "status": "GENERATED",
        "production_delivery_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "external_evidence_status": "NOT_RUN",
        "p0_launch_scope": {
            "id": p0_scope["scope_id"],
            "sha256": sha256_bytes(canonical_json(p0_scope)),
            "request_status": "IN_SCOPE" if not p0_blockers else "OUT_OF_SCOPE",
            "blockers": p0_blockers,
        },
        "supply_chain": {
            "sbom": {
                "path": SBOM_PATH,
                "format": "CycloneDX",
                "spec_version": dependency_sbom["specVersion"],
                "sha256": manifest_entry_by_path[SBOM_PATH]["sha256"],
                "transitive_inventory_status": sbom_status(
                    dependency_sbom, "elmos:transitive-inventory-status"
                ),
                "artifact_integrity_status": sbom_status(
                    dependency_sbom, "elmos:artifact-integrity-status"
                ),
                "dependency_graph_status": sbom_status(
                    dependency_sbom, "elmos:dependency-graph-status"
                ),
            },
            "release_manifest_status": "NOT_CREATED",
            "release_signature_status": "NOT_RUN",
            "trusted_root_status": "NOT_RUN",
        },
        "documentation": {
            "status": DOCUMENTATION_STATUS,
            "external_review_status": "NOT_RUN",
            "paths": sorted(DOCUMENT_SOURCE_REFS),
        },
        "insights": {
            "schema_version": project_insights["schema_version"],
            "status": project_insights["stage"],
            "path": insight_path,
            "report_path": insight_report_path,
            "direct_semantic_equivalence_status": "NOT_RUN",
            "direct_behavior_equivalence_status": "NOT_RUN",
        },
        "graphs": [
            {
                "kind": "project-structure",
                "path": PROJECT_STRUCTURE_PATH,
                "schema_id": "elmos.project-synthesis.project-structure.v1",
                "sha256": manifest_entry_by_path[PROJECT_STRUCTURE_PATH]["sha256"],
            },
            {
                "kind": "declared-dependency",
                "path": DEPENDENCY_GRAPH_PATH,
                "schema_id": "elmos.project-synthesis.declared-dependency-graph.v1",
                "sha256": manifest_entry_by_path[DEPENDENCY_GRAPH_PATH]["sha256"],
            },
        ],
        "files": manifest_entries,
    }
    files[".elmos/generation-manifest.json"] = pretty_json(manifest)
    return files


def _load_existing_manifest(root: Path) -> dict[str, Any] | None:
    path = root / ".elmos" / "generation-manifest.json"
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkspaceConflictError("EXISTING_MANIFEST_INVALID") from error
    if not isinstance(loaded, dict):
        raise WorkspaceConflictError("EXISTING_MANIFEST_INVALID")
    return loaded


def _assert_existing_files_unmodified(root: Path, manifest: dict[str, Any]) -> None:
    if (
        manifest.get("engine") != "elmos.project-synthesis"
        or manifest.get("engine_version") not in COMPATIBLE_MANIFEST_VERSIONS
        or manifest.get("status") != "GENERATED"
    ):
        raise WorkspaceConflictError("EXISTING_MANIFEST_IDENTITY_INVALID")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise WorkspaceConflictError("EXISTING_MANIFEST_FILES_INVALID")
    seen_paths: set[str] = set()
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("path"), str)
            or entry["path"] in seen_paths
            or not isinstance(entry.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None
        ):
            raise WorkspaceConflictError("EXISTING_MANIFEST_ENTRY_INVALID")
        seen_paths.add(entry["path"])
        target = _safe_path(root, entry["path"])
        if not target.is_file():
            raise WorkspaceConflictError(f"MANAGED_FILE_MISSING:{entry['path']}")
        if hashlib.sha256(target.read_bytes()).hexdigest() != entry.get("sha256"):
            raise WorkspaceConflictError(f"MANAGED_FILE_MODIFIED:{entry['path']}")


def _write_text_atomic(target: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.elmos-",
        suffix=".tmp",
        dir=target.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o755 if target.suffix == ".sh" else 0o644)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def generate_workspace(request_mapping: dict[str, Any], output: Path) -> dict[str, Any]:
    request = SynthesisRequest.from_mapping(request_mapping, require_approval=True)
    root = output.expanduser().resolve(strict=False)
    if root == Path(root.anchor) or root == Path.home().resolve():
        raise WorkspaceConflictError("BROAD_OUTPUT_TARGET_REJECTED")
    existing_manifest = _load_existing_manifest(root) if root.exists() else None
    if root.exists() and any(root.iterdir()) and existing_manifest is None:
        raise WorkspaceConflictError("NONEMPTY_UNMANAGED_OUTPUT_REJECTED")
    if existing_manifest is not None:
        _assert_existing_files_unmodified(root, existing_manifest)
        if existing_manifest.get("request_sha256") != request.request_hash:
            raise WorkspaceConflictError("REQUEST_BASELINE_CHANGED_REQUIRES_NEW_OUTPUT")
    rendered = render_workspace(request)
    for relative, content in sorted(rendered.items()):
        target = _safe_path(root, relative)
        if target.exists():
            if target.is_symlink() or not target.is_file():
                raise WorkspaceConflictError(f"GENERATED_TARGET_NOT_REGULAR_FILE:{relative}")
            if target.read_text(encoding="utf-8") == content:
                continue
            if existing_manifest is None:
                raise WorkspaceConflictError(f"EXISTING_FILE_CONFLICT:{relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_text_atomic(target, content)
    manifest = cast(dict[str, Any], json.loads(rendered[".elmos/generation-manifest.json"]))
    manifest["workspace"] = str(root)
    manifest["file_count"] = len(manifest["files"])
    return manifest
