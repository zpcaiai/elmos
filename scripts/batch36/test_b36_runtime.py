"""Test suite verifying all 18 Batch 36 Developer Experience skills in B36SkillRuntime."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from scripts.batch36.b36_skill_runtime import B36SkillRuntime


@pytest.fixture
def runtime():
    return B36SkillRuntime()


def test_runtime_skill_enumeration(runtime):
    assert len(runtime.SKILLS) == 18
    for s in runtime.SKILLS:
        assert s.startswith("b36-")


def test_b36_developer_workflow_factory(runtime):
    res = runtime.dispatch("b36-developer-workflow-factory", "init", {"client_type": "vscode"})
    assert res["factory_id"] == "fac-devex-vscode"
    assert "vscode" in res["supported_clients"]
    assert res["status"] == "INITIALIZED"


def test_b36_code_ownership_protected_regions(runtime):
    res = runtime.dispatch("b36-code-ownership-protected-regions", "check", {
        "file_content": "// USER_CODE_START\nint custom = 1;\n// USER_CODE_END"
    })
    assert res["protected_regions_detected"] == 1
    assert res["overwrite_blocked"] is True
    assert res["status"] == "PROTECTED"


def test_b36_developer_telemetry_privacy(runtime):
    res = runtime.dispatch("b36-developer-telemetry-privacy", "sanitize", {
        "events": [{"event": "preview", "user_email": "dev@internal.com"}]
    })
    assert res["pii_redacted"] is True
    assert res["sanitized_events"][0]["user_email"] == "[REDACTED_PII]"
    assert res["status"] == "COMPLIANT"


def test_b36_diagnostic_quick_fix(runtime):
    res = runtime.dispatch("b36-diagnostic-quick-fix", "get_fixes", {
        "diagnostic_code": "JAVA_PACKAGE_DEPRECATED"
    })
    assert len(res["quick_fixes"]) >= 1
    assert res["quick_fixes"][0]["safe"] is True
    assert res["status"] == "FIX_AVAILABLE"


def test_b36_enterprise_cli(runtime):
    res = runtime.dispatch("b36-enterprise-cli", "exec", {
        "subcommand": "assess",
        "args": ["--path", "."]
    })
    assert res["exit_code"] == 0
    assert "assess" in res["command"]
    assert res["status"] == "SUCCESS"


def test_b36_generated_code_explainability(runtime):
    res = runtime.dispatch("b36-generated-code-explainability", "explain", {
        "token": "@RestController"
    })
    assert res["target_construct"] == "@RestController"
    assert "applied_rule" in res
    assert res["confidence_score"] >= 0.90


def test_b36_ide_protocol_lsp_agent_bridge(runtime):
    res = runtime.dispatch("b36-ide-protocol-lsp-agent-bridge", "request", {
        "method": "textDocument/definition",
        "uri": "file:///src/App.java"
    })
    assert res["bridge_status"] == "CONNECTED"
    assert "hover" in res["capabilities"]


def test_b36_intellij_plugin(runtime):
    res = runtime.dispatch("b36-intellij-plugin", "invoke", {
        "action": "TriggerMigrationPreview"
    })
    assert res["plugin_id"] == "com.elmos.intellij.migration"
    assert res["status"] == "ACTIVE"


def test_b36_local_eval_affected_tests(runtime):
    res = runtime.dispatch("b36-local-eval-affected-tests", "select", {
        "modified_files": ["src/Service.java"],
        "total_test_count": 100,
    })
    assert res["affected_test_count"] == 2
    assert res["reduction_percent"] == 98.0
    assert res["status"] == "SELECTION_COMPLETE"


def test_b36_local_migration_preview(runtime):
    res = runtime.dispatch("b36-local-migration-preview", "preview", {
        "files": ["src/Controller.java"]
    })
    assert res["preview_mode"] == "DRY_RUN_OVERLAY"
    assert res["disk_mutations"] == 0
    assert res["status"] == "PREVIEW_GENERATED"


def test_b36_offline_private_developer_workflow(runtime):
    res = runtime.dispatch("b36-offline-private-developer-workflow", "verify_offline", {
        "offline_mode": True
    })
    assert res["network_egress_blocked"] is True
    assert res["status"] == "OFFLINE_VERIFIED"


def test_b36_pr_bot(runtime):
    res = runtime.dispatch("b36-pr-bot", "post_comment", {
        "pr_id": "PR-55",
        "platform": "GitHub",
    })
    assert res["comment_posted"] is True
    assert res["status"] == "POSTED"


def test_b36_recipe_mapping_authoring(runtime):
    res = runtime.dispatch("b36-recipe-mapping-authoring", "validate_recipe", {
        "recipe": {"name": "test_rule"}
    })
    assert res["syntax_valid"] is True
    assert res["validation_status"] == "AUTHORING_VALIDATED"


def test_b36_review_collaboration_approvals(runtime):
    res = runtime.dispatch("b36-review-collaboration-approvals", "check_approvals", {
        "reviewers": ["lead@corp.internal"],
        "approvals": ["lead@corp.internal"],
    })
    assert res["quorum_met"] is True
    assert res["status"] == "APPROVED"


def test_b36_semantic_conflict_resolution(runtime):
    res = runtime.dispatch("b36-semantic-conflict-resolution", "resolve_conflict", {
        "base": "def a(): pass",
        "generated": "def a(): x=1; pass",
        "latest": "def a(): y=2; pass",
    })
    assert res["conflicts_detected"] == 0
    assert res["status"] == "RESOLVED_CLEANLY"


def test_b36_source_target_navigation(runtime):
    res = runtime.dispatch("b36-source-target-navigation", "navigate", {
        "source_location": {"file": "A.cs", "line": 10, "col": 5}
    })
    assert res["bidirectional_verified"] is True
    assert res["status"] == "NAVIGATION_LINKED"


def test_b36_visual_studio_vscode_extensions(runtime):
    res = runtime.dispatch("b36-visual-studio-vscode-extensions", "init_extension", {
        "host_ide": "vscode"
    })
    assert res["webview_ready"] is True
    assert "elmos.preview" in res["commands_registered"]


def test_b36_developer_experience_certification_gate(runtime):
    res_pass = runtime.dispatch("b36-developer-experience-certification-gate", "gate", {
        "evidence": {
            "cli_verified": True,
            "ide_verified": True,
            "offline_verified": True,
            "privacy_verified": True,
            "latency_under_500ms": True,
        }
    })
    assert res_pass["gate_decision"] == "PASSED"
    assert res_pass["certification_status"] == "CERTIFIED"

    res_fail = runtime.dispatch("b36-developer-experience-certification-gate", "gate", {
        "evidence": {
            "cli_verified": False,
        }
    })
    assert res_fail["gate_decision"] == "REJECTED"


def test_unknown_skill_raises(runtime):
    with pytest.raises(KeyError):
        runtime.dispatch("b36-unknown", "op")
