from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import SynthesisRequest
from .rendering import clean

INSIGHTS_SCHEMA_VERSION = "1.0.0"
INSIGHT_STATUSES = ("PASSED", "FAILED", "NOT_RUN", "UNKNOWN", "NOT_APPLICABLE")


def _status_counts(statuses: list[str]) -> dict[str, int]:
    return {status: statuses.count(status) for status in INSIGHT_STATUSES}


def _semantic_subjects(request: SynthesisRequest) -> list[dict[str, Any]]:
    raw = request.raw
    dimensions = (
        ("requirements", "Approved requirements", raw["requirements"]),
        ("entities", "Entities", raw["entities"]),
        (
            "fields",
            "Entity fields",
            [field for entity in raw["entities"] for field in entity["fields"]],
        ),
        ("relations", "Entity relations", raw["relations"]),
        ("business-rules", "Business rules", raw["business_rules"]),
        ("permissions", "Permission declarations", raw["permissions"]),
        ("acceptance-criteria", "Acceptance criteria", raw["acceptance_criteria"]),
    )
    return [
        {
            "id": identifier,
            "label": label,
            "source_count": len(items),
            "mapped_count": len(items),
            "mapping_status": "PASSED",
            "semantic_equivalence_status": "NOT_RUN",
            "evidence_strength": "HASH_BOUND_TRACEABILITY",
        }
        for identifier, label, items in dimensions
    ]


def _structure(request: SynthesisRequest) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {
            "id": "approved",
            "label": "Approved request",
            "kind": "baseline",
            "path": "requirements/approved-request.json",
            "status": "PASSED",
        },
        {
            "id": "psir",
            "label": "Typed PSIR",
            "kind": "semantic-ir",
            "path": "requirements/psir.json",
            "status": "PASSED",
        },
        {
            "id": "blueprint",
            "label": "Project blueprint",
            "kind": "architecture",
            "path": "requirements/project-blueprint.json",
            "status": "PASSED",
        },
        {
            "id": "docs",
            "label": "Architecture and handoff docs",
            "kind": "documentation",
            "path": "docs/",
            "status": "PASSED",
        },
        {"id": "deploy", "label": "Deployment assets", "kind": "deployment", "path": "deploy/", "status": "PASSED"},
        {
            "id": "evidence",
            "label": "Verification evidence",
            "kind": "evidence",
            "path": ".elmos/verification.json",
            "status": "NOT_RUN",
        },
    ]
    edges: list[dict[str, str]] = [
        {"from": "approved", "to": "psir", "relation": "normalizes"},
        {"from": "psir", "to": "blueprint", "relation": "plans"},
        {"from": "blueprint", "to": "docs", "relation": "documents"},
        {"from": "blueprint", "to": "deploy", "relation": "configures"},
    ]
    for target in request.targets:
        node_id = f"target-{target.language}"
        nodes.append(
            {
                "id": node_id,
                "label": f"{target.language} · {target.framework} {target.runtime}",
                "kind": "generated-target",
                "language": target.language,
                "path": str(target.language if target.language != "csharp" else "dotnet"),
                "status": "PASSED",
            }
        )
        edges.extend(
            [
                {"from": "blueprint", "to": node_id, "relation": "generates"},
                {"from": node_id, "to": "evidence", "relation": "requires-verification"},
            ]
        )
    return {
        "graph_kind": "project-synthesis-insight-graph",
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "target_count": len(request.targets),
    }


def _cross_target_matrix(languages: list[str]) -> list[dict[str, str]]:
    return [
        {
            "source": source,
            "target": target,
            "semantic_status": "NOT_APPLICABLE" if source == target else "NOT_RUN",
            "behavior_status": "NOT_APPLICABLE" if source == target else "NOT_RUN",
            "reason": ("SAME_TARGET" if source == target else "DIRECT_PAIRWISE_SOURCE_TARGET_COMPARISON_NOT_EXECUTED"),
        }
        for source in languages
        for target in languages
    ]


def render_generation_insights(
    request: SynthesisRequest,
    *,
    project_structure: dict[str, Any],
    declared_dependencies: dict[str, Any],
) -> dict[str, Any]:
    languages = [target.language for target in request.targets]
    semantic_subjects = _semantic_subjects(request)
    return {
        "schema_version": INSIGHTS_SCHEMA_VERSION,
        "kind": "elmos.project-generation-insights",
        "stage": "GENERATED",
        "project": {
            "id": request.raw["project"]["id"],
            "name": request.project_name,
            "request_sha256": request.request_hash,
            "approved_payload_sha256": request.raw["approval"]["approved_payload_sha256"],
        },
        "claim_ceiling": "LOCAL_ENGINEERING_EVIDENCE",
        "project_structure": project_structure,
        "declared_dependencies": declared_dependencies,
        "structure": _structure(request),
        "semantic": {
            "relation": "APPROVED_REQUIREMENTS_TO_GENERATED_TARGETS",
            "mapping_status": "PASSED",
            "equivalence_status": "NOT_RUN",
            "subjects": semantic_subjects,
            "source_subject_count": sum(item["source_count"] for item in semantic_subjects),
            "mapped_subject_count": sum(item["mapped_count"] for item in semantic_subjects),
            "limitations": [
                "Hash-bound traceability proves provenance and mapping, not source/target semantic equivalence.",
                "Greenfield generation has no executable pre-conversion source artifact to compare.",
            ],
        },
        "behavior": {
            "profile": "native-build-test-startup-v1",
            "status": "NOT_RUN",
            "targets": [
                {
                    "language": language,
                    "status": "NOT_RUN",
                    "exact_toolchain_status": "NOT_RUN",
                    "build_analysis": {"total": 0, "status_counts": _status_counts([])},
                    "startup_status": "NOT_RUN",
                }
                for language in languages
            ],
            "cross_target_matrix": _cross_target_matrix(languages),
            "limitations": [
                "Generated source is not behavior evidence until native checks execute.",
                "Independent target passes do not imply pairwise behavioral equivalence.",
            ],
        },
        "coverage": [
            {
                "id": "project-structure",
                "label": "Project structure inventory",
                "status": "PASSED",
                "passed": 1,
                "total": 1,
            },
            {
                "id": "requirements-traceability",
                "label": "Requirement traceability",
                "status": "PASSED",
                "passed": len(semantic_subjects),
                "total": len(semantic_subjects),
            },
            {
                "id": "native-target-verification",
                "label": "Native target verification",
                "status": "NOT_RUN",
                "passed": 0,
                "total": len(languages),
            },
            {
                "id": "direct-semantic-equivalence",
                "label": "Direct semantic equivalence",
                "status": "NOT_RUN",
                "passed": 0,
                "total": len(languages) * max(0, len(languages) - 1),
            },
            {
                "id": "direct-behavior-equivalence",
                "label": "Direct behavior equivalence",
                "status": "NOT_RUN",
                "passed": 0,
                "total": len(languages) * max(0, len(languages) - 1),
            },
        ],
        "external_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }


def _load_generated_insights(workspace: Path) -> dict[str, Any]:
    path = workspace / "requirements" / "project-insights.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("PROJECT_INSIGHTS_INVALID") from error
    if (
        not isinstance(loaded, dict)
        or loaded.get("schema_version") != INSIGHTS_SCHEMA_VERSION
        or loaded.get("kind") != "elmos.project-generation-insights"
        or loaded.get("stage") != "GENERATED"
    ):
        raise RuntimeError("PROJECT_INSIGHTS_INVALID")
    return loaded


def verified_generation_insights(workspace: Path, evidence: dict[str, Any]) -> dict[str, Any]:
    generated = _load_generated_insights(workspace)
    behavior = generated.get("behavior")
    if not isinstance(behavior, dict) or not isinstance(behavior.get("targets"), list):
        raise RuntimeError("PROJECT_INSIGHTS_BEHAVIOR_INVALID")
    results = evidence.get("results")
    environment = evidence.get("environment")
    if not isinstance(results, list) or not isinstance(environment, dict):
        raise RuntimeError("PROJECT_INSIGHTS_EVIDENCE_INVALID")
    exact_matches = environment.get("exact_toolchain_match")
    if not isinstance(exact_matches, dict):
        raise RuntimeError("PROJECT_INSIGHTS_EVIDENCE_INVALID")

    verified_targets: list[dict[str, Any]] = []
    for planned in behavior["targets"]:
        if not isinstance(planned, dict) or not isinstance(planned.get("language"), str):
            raise RuntimeError("PROJECT_INSIGHTS_TARGET_INVALID")
        language = planned["language"]
        target_results = [item for item in results if isinstance(item, dict) and item.get("language") == language]
        native_results = [item for item in target_results if item.get("kind") not in {"toolchain", "startup-probe"}]
        startup = next((item for item in target_results if item.get("kind") == "startup-probe"), None)
        statuses = [str(item.get("status", "UNKNOWN")) for item in native_results]
        native_status = (
            "FAILED"
            if "FAILED" in statuses
            else "NOT_RUN"
            if not native_results or "NOT_RUN" in statuses
            else "UNKNOWN"
            if any(status not in INSIGHT_STATUSES for status in statuses)
            else "PASSED"
        )
        startup_status = str(startup.get("status", "NOT_RUN")) if isinstance(startup, dict) else "NOT_RUN"
        toolchain_statuses = [
            str(item.get("status", "UNKNOWN")) for item in target_results if item.get("kind") == "toolchain"
        ]
        exact_status = (
            "PASSED"
            if exact_matches.get(language) is True
            else "FAILED"
            if "FAILED" in toolchain_statuses
            else "UNKNOWN"
            if any(status not in INSIGHT_STATUSES for status in toolchain_statuses)
            else "NOT_RUN"
        )
        overall = (
            "FAILED"
            if "FAILED" in {exact_status, native_status, startup_status}
            else "PASSED"
            if exact_status == native_status == startup_status == "PASSED"
            else "UNKNOWN"
            if "UNKNOWN" in {exact_status, native_status, startup_status}
            else "NOT_RUN"
        )
        verified_targets.append(
            {
                "language": language,
                "status": overall,
                "exact_toolchain_status": exact_status,
                "build_analysis": {
                    "total": len(native_results),
                    "status_counts": _status_counts(statuses),
                },
                "startup_status": startup_status,
            }
        )

    target_statuses = [str(target["status"]) for target in verified_targets]
    behavior["targets"] = verified_targets
    behavior["status"] = (
        "FAILED"
        if "FAILED" in target_statuses
        else "PASSED"
        if target_statuses and all(status == "PASSED" for status in target_statuses)
        else "UNKNOWN"
        if "UNKNOWN" in target_statuses
        else "NOT_RUN"
    )
    generated["stage"] = "VERIFIED"
    generated["behavior"] = behavior
    for dimension in generated.get("coverage", []):
        if isinstance(dimension, dict) and dimension.get("id") == "native-target-verification":
            passed = target_statuses.count("PASSED")
            dimension["passed"] = passed
            dimension["status"] = behavior["status"]
    generated["verification_status"] = evidence.get("status", "UNKNOWN")
    return generated


def _markdown_cell(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "\\|")
        .replace("`", "\\`")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _mermaid_label(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("[", "(")
        .replace("]", ")")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _mermaid_graph(graph: dict[str, Any], *, direction: str) -> str:
    raw_nodes = graph.get("nodes")
    raw_edges = graph.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        raise RuntimeError("PROJECT_INSIGHTS_GRAPH_INVALID")
    node_indexes: dict[str, str] = {}
    lines = [f"flowchart {direction}"]
    for index, node in enumerate(raw_nodes):
        if not isinstance(node, dict) or not isinstance(node.get("id"), str):
            raise RuntimeError("PROJECT_INSIGHTS_GRAPH_INVALID")
        graph_id = f"N{index}"
        node_indexes[node["id"]] = graph_id
        label_parts = [str(node.get("label", node.get("coordinate", node["id"])))]
        if isinstance(node.get("path"), str):
            label_parts.append(str(node["path"]))
        elif isinstance(node.get("coordinate"), str):
            label_parts.append(str(node["coordinate"]))
        label = _mermaid_label(" · ".join(label_parts))
        lines.append(f'  {graph_id}["{label}"]')
    for edge in raw_edges:
        if not isinstance(edge, dict):
            raise RuntimeError("PROJECT_INSIGHTS_GRAPH_INVALID")
        source = node_indexes.get(str(edge.get("from")))
        target = node_indexes.get(str(edge.get("to")))
        if source is None or target is None:
            raise RuntimeError("PROJECT_INSIGHTS_GRAPH_INVALID")
        relation = _mermaid_label(edge.get("type", edge.get("relation", "relates")))
        lines.append(f"  {source} -->|{relation}| {target}")
    return "\n".join(lines)


def _template_block(value: str) -> str:
    """Keep multiline interpolation aligned with the surrounding clean() template."""

    return value.replace("\n", "\n        ")


def render_insights_markdown(request: SynthesisRequest, insights: dict[str, Any]) -> str:
    languages = [target.language for target in request.targets]
    target_nodes = "\n".join(
        f'  BLUEPRINT --> {language.upper()}["{language} target"] --> VERIFY["Native verification · NOT_RUN"]'
        for language in languages
    )
    semantic_rows = "\n".join(
        f"| {_markdown_cell(subject['label'])} | {subject['source_count']} | {subject['mapped_count']} | "
        f"`{subject['mapping_status']}` | `{subject['semantic_equivalence_status']}` |"
        for subject in insights["semantic"]["subjects"]
    )
    matrix_header = "| Source \\ Target | " + " | ".join(languages) + " |"
    matrix_divider = "|---|" + "|".join("---" for _ in languages) + "|"
    matrix_rows = "\n".join(
        "| " + source + " | " + " | ".join("N/A" if source == target else "NOT_RUN" for target in languages) + " |"
        for source in languages
    )
    structure_graph = _template_block(_mermaid_graph(insights["project_structure"], direction="TB"))
    dependency_graph = _template_block(_mermaid_graph(insights["declared_dependencies"], direction="LR"))
    target_nodes = _template_block(target_nodes)
    semantic_rows = _template_block(semantic_rows)
    matrix_rows = _template_block(matrix_rows)
    coverage_rows = "\n".join(
        f"| {_markdown_cell(item['label'])} | `{item['status']}` | {item['passed']} | {item['total']} |"
        for item in insights["coverage"]
    )
    target_rows = "\n".join(
        f"| `{item['language']}` | `{item['exact_toolchain_status']}` | "
        f"`{item['status']}` | `{item['startup_status']}` |"
        for item in insights["behavior"]["targets"]
    )
    coverage_rows = _template_block(coverage_rows)
    target_rows = _template_block(target_rows)
    return clean(
        f"""
        # Project structure and equivalence insights

        Project: `{_markdown_cell(request.project_name)}`<br>
        Approved baseline: `sha256:{request.raw["approval"]["approved_payload_sha256"]}`<br>
        Report stage: `GENERATED` · claim ceiling: `LOCAL_ENGINEERING_EVIDENCE`

        ## Overall generation structure

        ```mermaid
        flowchart LR
          APPROVED["Approved request"] --> PSIR["Typed PSIR"] --> BLUEPRINT["Project blueprint"]
        {target_nodes}
          BLUEPRINT --> DOCS["Architecture / database / migration docs"]
          BLUEPRINT --> DEPLOY["Container / Kubernetes / deployment handoff"]
        ```

        ## Generated repository structure

        ```mermaid
        {structure_graph}
        ```

        The structure graph inventories every manifest-managed generated artifact. Its machine-readable
        source is `requirements/project-structure.json`; unclassified paths fail verification closed.

        ## Declared dependency graph

        ```mermaid
        {dependency_graph}
        ```

        These are declared direct runtime, framework, build-tool, and provider dependencies. Native
        transitive resolution remains `NOT_RUN`; the graph must not be read as a resolved SBOM.

        ## Semantic mapping and equivalence

        | Dimension | Source subjects | Hash-bound mappings | Mapping | Direct semantic equivalence |
        |---|---:|---:|---|---|
        {semantic_rows}

        Mapping coverage records deterministic provenance and traceability. It is not a proof that
        arbitrary source-program semantics were preserved. Greenfield generation has no executable
        pre-conversion source artifact, so direct semantic equivalence remains `NOT_RUN`.

        ## Direct cross-target behavior matrix

        {matrix_header}
        {matrix_divider}
        {matrix_rows}

        Every off-diagonal cell remains `NOT_RUN` until the exact two targets are run against one
        independently governed behavior corpus and their normalized observations are compared.
        Native build/test/startup evidence is written to `.elmos/verification.json` by the governed
        verification pipeline; independent verification and certification remain separate gates.

        ## Native target evidence

        | Target | Exact toolchain | Build/test/startup aggregate | Startup |
        |---|---|---|---|
        {target_rows}

        ## Multi-dimensional completion

        | Dimension | Status | Passed | Total |
        |---|---|---:|---:|
        {coverage_rows}

        The rows above intentionally remain separate. They are not averaged into one confidence score;
        `NOT_RUN` remains in the denominator, and external verification is `NOT_RUN` while certification
        is `NOT_CERTIFIED`.
        """
    )
