from __future__ import annotations

import json
from pathlib import Path

from elmos_project_synthesis.insights import (
    render_insights_markdown,
    verified_generation_insights,
)
from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SUPPORTED_LANGUAGES, SynthesisRequest
from elmos_project_synthesis.workspace import generate_workspace, render_workspace


def _request() -> SynthesisRequest:
    draft = create_draft(
        name="insight-service",
        description="管理客户订单并显示生成结构与等价证据。",
        entities=(
            {
                "singular": "customer",
                "plural": "customers",
                "fields": [{"name": "display_name", "type": "string", "required": True}],
            },
            {
                "singular": "order",
                "plural": "orders",
                "fields": [{"name": "total", "type": "number", "required": True}],
            },
        ),
        business_rules=("order.total must be non-negative",),
        languages=SUPPORTED_LANGUAGES,
    )
    return SynthesisRequest.from_mapping(approve_request(draft, actor="user:insight-reviewer"))


def _passing_evidence() -> dict[str, object]:
    results: list[dict[str, object]] = []
    for language in SUPPORTED_LANGUAGES:
        results.extend(
            [
                {
                    "language": language,
                    "kind": "toolchain",
                    "status": "PASSED",
                    "command": ["tool", "--version"],
                },
                {
                    "language": language,
                    "kind": "build-analysis",
                    "status": "PASSED",
                    "command": ["tool", "test"],
                },
                {
                    "language": language,
                    "kind": "startup-probe",
                    "status": "PASSED",
                    "command": ["tool", "run"],
                },
            ]
        )
    return {
        "schema_version": "1.1.0",
        "status": "PASSED",
        "environment": {
            "exact_toolchain_match": {language: True for language in SUPPORTED_LANGUAGES},
        },
        "results": results,
    }


def test_generated_insights_cover_structure_semantics_and_complete_pair_matrix() -> None:
    request = _request()
    first_files = render_workspace(request)
    second_files = render_workspace(request)
    first = json.loads(first_files["requirements/project-insights.json"])
    second = json.loads(second_files["requirements/project-insights.json"])

    assert first == second
    assert first["stage"] == "GENERATED"
    assert first["structure"]["target_count"] == 8
    assert first["project_structure"]["coverage"]["represented_application_count"] == 8
    assert first["declared_dependencies"]["resolution"]["status"] == "NOT_RUN"
    assert first["declared_dependencies"]["complete"] is False
    assert {node.get("language") for node in first["structure"]["nodes"] if node.get("language")} == set(
        SUPPORTED_LANGUAGES
    )
    assert first["semantic"]["mapping_status"] == "PASSED"
    assert first["semantic"]["equivalence_status"] == "NOT_RUN"
    assert first["semantic"]["source_subject_count"] == first["semantic"]["mapped_subject_count"]

    matrix = first["behavior"]["cross_target_matrix"]
    assert len(matrix) == len(SUPPORTED_LANGUAGES) ** 2
    assert sum(item["behavior_status"] == "NOT_APPLICABLE" for item in matrix) == len(SUPPORTED_LANGUAGES)
    assert sum(item["behavior_status"] == "NOT_RUN" for item in matrix) == (
        len(SUPPORTED_LANGUAGES) * (len(SUPPORTED_LANGUAGES) - 1)
    )


def test_generated_workspace_contains_machine_and_human_readable_charts() -> None:
    request = _request()
    files = render_workspace(request)
    manifest = json.loads(files[".elmos/generation-manifest.json"])
    insights = json.loads(files["requirements/project-insights.json"])
    markdown = files["docs/PROJECT_INSIGHTS.md"]

    assert manifest["engine_version"] == "1.4.0"
    assert manifest["insights"]["path"] == "requirements/project-insights.json"
    assert manifest["insights"]["direct_behavior_equivalence_status"] == "NOT_RUN"
    assert insights["project"]["request_sha256"] == request.request_hash
    assert "```mermaid" in markdown
    assert 'BLUEPRINT --> JAVA["java target"]' in markdown
    assert "Direct cross-target behavior matrix" in markdown
    assert "NOT_RUN" in markdown


def test_verified_insights_promote_only_native_target_checks(tmp_path: Path) -> None:
    request = _request()
    workspace = tmp_path / "workspace"
    generate_workspace(request.raw, workspace)

    verified = verified_generation_insights(workspace, _passing_evidence())

    assert verified["stage"] == "VERIFIED"
    assert verified["verification_status"] == "PASSED"
    assert verified["behavior"]["status"] == "PASSED"
    assert {target["status"] for target in verified["behavior"]["targets"]} == {"PASSED"}
    native = next(item for item in verified["coverage"] if item["id"] == "native-target-verification")
    assert native == {
        "id": "native-target-verification",
        "label": "Native target verification",
        "status": "PASSED",
        "passed": 8,
        "total": 8,
    }
    direct = next(item for item in verified["coverage"] if item["id"] == "direct-behavior-equivalence")
    assert direct["status"] == "NOT_RUN"
    assert direct["passed"] == 0
    assert verified["external_verification_status"] == "NOT_RUN"
    assert verified["certification_status"] == "NOT_CERTIFIED"


def test_missing_startup_keeps_behavior_not_run(tmp_path: Path) -> None:
    request = _request()
    workspace = tmp_path / "workspace"
    generate_workspace(request.raw, workspace)
    evidence = _passing_evidence()
    startup = next(
        item for item in evidence["results"] if item["language"] == "rust" and item["kind"] == "startup-probe"
    )
    startup["status"] = "NOT_RUN"
    evidence["status"] = "PARTIAL"

    verified = verified_generation_insights(workspace, evidence)

    assert verified["behavior"]["status"] == "NOT_RUN"
    rust = next(target for target in verified["behavior"]["targets"] if target["language"] == "rust")
    assert rust["status"] == "NOT_RUN"
    assert all(
        item["behavior_status"] == "NOT_RUN"
        for item in verified["behavior"]["cross_target_matrix"]
        if item["source"] != item["target"]
    )


def test_markdown_escapes_request_text() -> None:
    request = _request()
    insights = json.loads(render_workspace(request)["requirements/project-insights.json"])
    markdown = render_insights_markdown(request, insights)

    assert request.project_name in markdown
    assert "claim ceiling: `LOCAL_ENGINEERING_EVIDENCE`" in markdown
