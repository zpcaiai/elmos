"""Tests for Autonomous Intent Disambiguation & Zero-Human Intake Approval.
"""
from __future__ import annotations

import pytest

from elmos_project_synthesis.autonomous_intent_resolver import (
    AUTONOMOUS_GOVERNOR_ACTOR,
    auto_resolve_open_questions,
    autonomous_resolve_and_approve,
)
from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SynthesisRequest


def test_ambiguous_draft_generates_open_questions_and_blocks_human_approval():
    # A loose natural-language draft without clear entities or permissions in postgres production profile
    draft = create_draft(
        name="logistics-hub",
        description="A vague warehouse and logistics system with special manual business rules.",
        persistence="postgresql",
        auth_mode="jwt",
        business_rules=["Items should never be misplaced or lost manually"],
    )

    # Verify open questions were generated
    questions = draft.get("open_questions", [])
    assert len(questions) > 0

    # Verify human approval is blocked
    with pytest.raises(ValueError, match="OPEN_QUESTIONS_BLOCK_APPROVAL"):
        approve_request(draft, actor="human-operator@company.com")


def test_autonomous_resolve_clears_open_questions_and_records_journal():
    draft = create_draft(
        name="billing-service",
        description="A billing service needing auto resolution",
        persistence="postgresql",
        auth_mode="jwt",
        business_rules=["Invoices must be verified manually before approval"],
    )

    resolved_draft, journal = auto_resolve_open_questions(draft)

    # 1. All open questions cleared
    assert resolved_draft["open_questions"] == []
    assert len(journal) > 0

    # 2. Journal has audit entries
    strategies = [entry["strategy"] for entry in journal]
    assert any("INFER" in s or "SYNTHESIZE" in s or "NORMALIZE" in s for s in strategies)

    # 3. Rules compiled to application enforcement
    rules = resolved_draft.get("business_rules", [])
    assert len(rules) > 0
    assert all(r.get("enforcement") == "application" for r in rules)

    # 4. Permissions synthesized for JWT/OIDC
    permissions = resolved_draft.get("permissions", [])
    assert len(permissions) > 0
    assert any(p.get("action") == "create" and p.get("effect") == "allow" for p in permissions)


def test_autonomous_resolve_and_approve_produces_valid_synthesis_request():
    draft = create_draft(
        name="payment-gateway",
        description="High-security payment processing system",
        persistence="postgresql",
        auth_mode="jwt",
        languages=["python", "go"],
    )

    approved = autonomous_resolve_and_approve(draft)

    # Check approval structure
    assert approved["approval"]["status"] == "APPROVED"
    assert approved["approval"]["approved_by"] == AUTONOMOUS_GOVERNOR_ACTOR
    assert approved["approval"]["autonomous_decision"] is True
    assert "approved_payload_sha256" in approved["approval"]

    # Verify SynthesisRequest instantiates without any error
    req = SynthesisRequest.from_mapping(approved, require_approval=True)
    assert req.project_name == "payment-gateway"
    assert req.raw["approval"]["status"] == "APPROVED"
    assert len(req.entities) > 0
