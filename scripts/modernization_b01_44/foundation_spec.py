#!/usr/bin/env python3
"""Domain field specifications for the Batch 01-05 foundation schemas.

Batches 01-05 ship bespoke schemas rather than the uniform Batch 06-44 set.
Each entry below is the typed contract for one of those schemas: the shared
envelope (id / version / scope / evidence_refs) plus the fields that make the
record mean something specific.  ``required`` names are enforced; every schema
is closed (``additionalProperties: false``) so the trust boundary rejects
anything unmodelled.
"""

from __future__ import annotations

from typing import Any

STR = {"type": "string", "minLength": 1}
STRS = {"type": "array", "items": {"type": "string"}}
BOOL = {"type": "boolean"}
INT = {"type": "integer"}
DIGEST = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
DIGESTS = {"type": "array", "items": DIGEST}
INSTANT = {"type": "string", "format": "date-time"}
DECIMAL = {"type": "string", "pattern": "^-?[0-9]+(\\.[0-9]+)?$"}

TRUST_LEVELS = [
    "measured",
    "compiler-confirmed",
    "deterministic",
    "runtime-observed",
    "independent-verified",
    "human-approved",
    "model-inferred",
    "unknown",
]
STATUSES = ["certified", "limited", "experimental", "blocked", "stale", "revoked"]
CONFIDENCE = ["verified", "corroborated", "single-source", "asserted", "unknown"]

#: schema file stem -> (title, extra properties, extra required)
FIELD_SPECS: dict[str, tuple[str, dict[str, Any], list[str]]] = {
    # -- Batch 01 ---------------------------------------------------------
    "competitor-record": (
        "CompetitorRecord",
        {
            "vendor_name": STR,
            "product_name": STR,
            "category": {"enum": ["platform", "codegen", "cloud-migration", "consulting", "point-tool"]},
            "aliases": STRS,
            "relationship": {"enum": ["independent", "acquired-by", "renamed-from", "oem-of", "fork-of"]},
            "related_to": STRS,
            "entity_resolution_reason": STR,
        },
        ["vendor_name", "product_name", "category"],
    ),
    "market-boundary": (
        "MarketBoundary",
        {
            "boundary_name": STR,
            "included_capabilities": STRS,
            "explicit_exclusions": STRS,
            "exclusion_rationale": STR,
        },
        ["boundary_name", "included_capabilities", "explicit_exclusions"],
    ),
    "capability-fact": (
        "CapabilityFact",
        {
            "competitor_id": STR,
            "capability_id": STR,
            "claim": STR,
            "confidence": {"enum": CONFIDENCE},
            "source_kind": {"enum": ["vendor-doc", "vendor-marketing", "third-party", "hands-on", "customer-report"]},
            "source_uri": STR,
            "observed_version": STR,
            "expires_at": INSTANT,
        },
        ["competitor_id", "capability_id", "claim", "confidence", "source_kind"],
    ),
    "capability-matrix": (
        "CapabilityMatrix",
        {
            "capability_ids": STRS,
            "competitor_ids": STRS,
            "cells": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["competitor_id", "capability_id", "level"],
                    "properties": {
                        "competitor_id": STR,
                        "capability_id": STR,
                        "level": {"enum": ["none", "partial", "full", "unknown"]},
                        "fact_refs": STRS,
                    },
                },
            },
        },
        ["capability_ids", "competitor_ids", "cells"],
    ),
    "route-coverage": (
        "RouteCoverage",
        {
            "source_stack": STR,
            "target_stack": STR,
            "direction": {"enum": ["forward", "reverse", "bidirectional"]},
            "coverage": {"enum": ["none", "declared", "demonstrated", "certified", "unknown"]},
            "fact_refs": STRS,
        },
        ["source_stack", "target_stack", "direction", "coverage"],
    ),
    "database-route": (
        "DatabaseRoute",
        {
            "source_engine": {"enum": ["oracle", "sqlserver", "mysql", "postgresql", "db2", "other"]},
            "target_engine": {"enum": ["oracle", "sqlserver", "mysql", "postgresql", "db2", "other"]},
            "schema_coverage": {"enum": ["none", "partial", "full", "unknown"]},
            "procedural_coverage": {"enum": ["none", "partial", "full", "unknown"]},
            "data_movement": {"enum": ["none", "bulk", "cdc", "dual-write", "unknown"]},
            "fact_refs": STRS,
        },
        ["source_engine", "target_engine", "schema_coverage", "procedural_coverage"],
    ),
    "trust-assessment": (
        "TrustAssessment",
        {
            "competitor_id": STR,
            "verification_model": {"enum": ["none", "self-reported", "test-based", "differential", "formal", "unknown"]},
            "evidence_disclosure": {"enum": ["none", "summary", "detailed", "reproducible"]},
            "independent_oracle": BOOL,
            "notes": STR,
        },
        ["competitor_id", "verification_model", "evidence_disclosure", "independent_oracle"],
    ),
    "positioning-decision": (
        "PositioningDecision",
        {
            "decision": STR,
            "differentiators": STRS,
            "explicit_non_goals": STRS,
            "supporting_fact_refs": STRS,
            "review_by": INSTANT,
        },
        ["decision", "differentiators", "explicit_non_goals"],
    ),
    "battlecard": (
        "Battlecard",
        {
            "competitor_id": STR,
            "our_strengths": STRS,
            "their_strengths": STRS,
            "verified_claims_only": BOOL,
            "legal_review": {"enum": ["required", "completed", "not-applicable"]},
            "fact_refs": STRS,
        },
        ["competitor_id", "our_strengths", "their_strengths", "verified_claims_only", "legal_review"],
    ),
    # -- Batch 02 ---------------------------------------------------------
    "assessment-request": (
        "AssessmentRequest",
        {
            "tenant_id": STR,
            "portfolio_id": STR,
            "requested_depth": {"enum": ["inventory", "structural", "semantic", "probe"]},
            "access_grants": STRS,
            "data_residency": STR,
        },
        ["tenant_id", "portfolio_id", "requested_depth"],
    ),
    "portfolio-source": (
        "PortfolioSource",
        {
            "source_kind": {"enum": ["git", "artifact", "binary", "document", "runtime-export"]},
            "locator": STR,
            "content_digest": DIGEST,
            "access_grant_ref": STR,
        },
        ["source_kind", "locator", "content_digest"],
    ),
    "workload-asset": (
        "WorkloadAsset",
        {
            "asset_kind": {"enum": ["application", "service", "batch-job", "database", "integration", "ui"]},
            "language": STR,
            "framework": STR,
            "loc": INT,
            "source_refs": STRS,
            "unknown_regions": STRS,
        },
        ["asset_kind", "source_refs"],
    ),
    "assessment-snapshot": (
        "AssessmentSnapshot",
        {
            "snapshot_digest": DIGEST,
            "taken_at": INSTANT,
            "source_digests": DIGESTS,
            "toolchain_pins": STRS,
        },
        ["snapshot_digest", "taken_at", "source_digests"],
    ),
    "architecture-graph": (
        "ArchitectureGraph",
        {
            "nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["node_id", "kind"],
                    "properties": {"node_id": STR, "kind": STR, "asset_ref": STR},
                },
            },
            "edges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["from_node", "to_node", "relation"],
                    "properties": {
                        "from_node": STR,
                        "to_node": STR,
                        "relation": STR,
                        "confidence": {"enum": CONFIDENCE},
                    },
                },
            },
            "recovered_by": {"enum": ["static", "runtime", "document", "mixed"]},
        },
        ["nodes", "edges", "recovered_by"],
    ),
    "dependency-edge": (
        "DependencyEdge",
        {
            "from_symbol": STR,
            "to_symbol": STR,
            "dependency_kind": {"enum": ["call", "import", "inherit", "reflect", "config", "unknown"]},
            "resolved": BOOL,
            "confidence": {"enum": CONFIDENCE},
        },
        ["from_symbol", "to_symbol", "dependency_kind", "resolved"],
    ),
    "dataflow-edge": (
        "DataflowEdge",
        {
            "producer": STR,
            "consumer": STR,
            "medium": {"enum": ["parameter", "field", "queue", "table", "file", "http", "unknown"]},
            "carries_pii": {"type": ["boolean", "null"]},
            "confidence": {"enum": CONFIDENCE},
        },
        ["producer", "consumer", "medium"],
    ),
    "assessment-finding": (
        "AssessmentFinding",
        {
            "finding_kind": {"enum": ["debt", "security", "compliance", "compatibility", "operability", "unknown"]},
            "severity": {"enum": ["critical", "high", "medium", "low", "info"]},
            "asset_refs": STRS,
            "statement": STR,
            "remediation": STR,
        },
        ["finding_kind", "severity", "asset_refs", "statement"],
    ),
    "cloud-fit": (
        "CloudFit",
        {
            "asset_ref": STR,
            "target_model": {"enum": ["rehost", "replatform", "refactor", "rearchitect", "retire", "retain"]},
            "blockers": STRS,
            "fit": {"enum": ["good", "conditional", "poor", "unknown"]},
        },
        ["asset_ref", "target_model", "fit"],
    ),
    "migration-candidate": (
        "MigrationCandidate",
        {
            "asset_ref": STR,
            "source_stack": STR,
            "target_stack": STR,
            "strategy": {"enum": ["rehost", "replatform", "refactor", "rearchitect", "rewrite"]},
            "blocking_unknowns": STRS,
        },
        ["asset_ref", "source_stack", "target_stack", "strategy"],
    ),
    "prediction-estimate": (
        "PredictionEstimate",
        {
            "subject_ref": STR,
            "metric": {"enum": ["effort-hours", "duration-days", "defect-rate", "automation-ratio"]},
            "point_estimate": DECIMAL,
            "interval_low": DECIMAL,
            "interval_high": DECIMAL,
            "calibration_sample_size": INT,
            "model_version": STR,
        },
        ["subject_ref", "metric", "point_estimate", "interval_low", "interval_high", "calibration_sample_size"],
    ),
    "wave-plan": (
        "WavePlan",
        {
            "waves": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["wave_index", "asset_refs"],
                    "properties": {
                        "wave_index": INT,
                        "asset_refs": STRS,
                        "blocked_by_waves": {"type": "array", "items": INT},
                    },
                },
            },
            "ordering_rationale": STR,
        },
        ["waves", "ordering_rationale"],
    ),
    "assessment-certificate": (
        "AssessmentCertificate",
        {
            "status": {"enum": STATUSES},
            "snapshot_digest": DIGEST,
            "coverage_numerator": INT,
            "coverage_denominator": INT,
            "unknown_count": INT,
            "issued_at": INSTANT,
            "expires_at": INSTANT,
        },
        [
            "status",
            "snapshot_digest",
            "coverage_numerator",
            "coverage_denominator",
            "unknown_count",
            "issued_at",
            "expires_at",
        ],
    ),
    # -- Batch 03 ---------------------------------------------------------
    "source-span": (
        "SourceSpan",
        {
            "file_path": STR,
            "start_line": INT,
            "start_column": INT,
            "end_line": INT,
            "end_column": INT,
            "file_digest": DIGEST,
        },
        ["file_path", "start_line", "start_column", "end_line", "end_column", "file_digest"],
    ),
    "symbol-identity": (
        "SymbolIdentity",
        {
            "symbol_id": STR,
            "qualified_name": STR,
            "kind": {"enum": ["module", "type", "function", "field", "parameter", "label", "unknown"]},
            "declared_in": STR,
            "linkage": {"enum": ["internal", "exported", "imported", "dynamic", "unknown"]},
        },
        ["symbol_id", "qualified_name", "kind", "linkage"],
    ),
    "type-ref": (
        "TypeRef",
        {
            "type_id": STR,
            "canonical_name": STR,
            "nullability": {"enum": ["non-null", "nullable", "unknown"]},
            "type_arguments": STRS,
            "numeric_precision": {"type": ["string", "null"]},
            "lossy_lowering": BOOL,
        },
        ["type_id", "canonical_name", "nullability", "lossy_lowering"],
    ),
    "semantic-fact": (
        "SemanticFact",
        {
            "node_id": STR,
            "predicate": STR,
            "value": STR,
            "derivation": {"enum": ["parsed", "inferred", "runtime-observed", "declared", "unknown"]},
            "span_ref": STR,
        },
        ["node_id", "predicate", "value", "derivation"],
    ),
    "ir-node-header": (
        "IRNodeHeader",
        {
            "node_id": STR,
            "node_kind": STR,
            "semantic_level": {"enum": ["syntax", "resolved", "typed", "effectful", "canonical"]},
            "children": STRS,
            "span_ref": STR,
            "unknown_reason": {"type": ["string", "null"]},
        },
        ["node_id", "node_kind", "semantic_level"],
    ),
    "provenance-edge": (
        "ProvenanceEdge",
        {
            "derived_node": STR,
            "origin_node": STR,
            "transform": STR,
            "lossless": BOOL,
        },
        ["derived_node", "origin_node", "transform", "lossless"],
    ),
    "language-extension-capsule": (
        "LanguageExtensionCapsule",
        {
            "language": STR,
            "language_version": STR,
            "feature": STR,
            "representation": {"enum": ["native", "lowered", "opaque"]},
            "opaque_payload_digest": {"type": ["string", "null"], "pattern": "^[a-f0-9]{64}$"},
        },
        ["language", "language_version", "feature", "representation"],
    ),
    "proof-obligation": (
        "ProofObligation",
        {
            "obligation_id": STR,
            "kind": {"enum": ["type-preservation", "evaluation-order", "exception-shape", "resource-release", "numeric-precision", "concurrency"]},
            "statement": STR,
            "discharged_by": {"enum": ["proof", "test", "differential", "review", "not-discharged"]},
            "node_refs": STRS,
        },
        ["obligation_id", "kind", "statement", "discharged_by"],
    ),
    "ir-bundle-manifest": (
        "IRBundleManifest",
        {
            "bundle_id": STR,
            "source_snapshot_digest": DIGEST,
            "frontend_id": STR,
            "frontend_version": STR,
            "node_count": INT,
            "unknown_node_count": INT,
            "semantic_level": {"enum": ["syntax", "resolved", "typed", "effectful", "canonical"]},
        },
        ["bundle_id", "source_snapshot_digest", "frontend_id", "frontend_version", "node_count", "unknown_node_count", "semantic_level"],
    ),
    "ir-certificate": (
        "IRCertificate",
        {
            "status": {"enum": STATUSES},
            "bundle_id": STR,
            "conformance_score": DECIMAL,
            "obligation_refs": STRS,
            "issued_at": INSTANT,
            "expires_at": INSTANT,
        },
        ["status", "bundle_id", "conformance_score", "issued_at", "expires_at"],
    ),
    # -- Batch 04 ---------------------------------------------------------
    "semantic-mapping": (
        "SemanticMapping",
        {
            "mapping_id": STR,
            "source_construct": STR,
            "target_construct": STR,
            "loss_class": {"enum": ["lossless", "normalized", "approximate", "requires-adapter", "unsupported"]},
            "preconditions": STRS,
        },
        ["mapping_id", "source_construct", "target_construct", "loss_class"],
    ),
    "transformation-rule": (
        "TransformationRule",
        {
            "rule_id": STR,
            "match": STR,
            "rewrite": STR,
            "guards": STRS,
            "direction": STR,
            "priority": INT,
        },
        ["rule_id", "match", "rewrite", "direction", "priority"],
    ),
    "compiled-rule-ir": (
        "CompiledRuleIR",
        {
            "rule_id": STR,
            "compiled_digest": DIGEST,
            "static_checks": STRS,
            "terminating": BOOL,
            "confluent": {"type": ["boolean", "null"]},
        },
        ["rule_id", "compiled_digest", "static_checks", "terminating"],
    ),
    "match-record": (
        "MatchRecord",
        {
            "rule_id": STR,
            "node_id": STR,
            "bindings": {"type": "object", "additionalProperties": True},
            "guard_results": STRS,
            "applicable": BOOL,
        },
        ["rule_id", "node_id", "applicable"],
    ),
    "patch-intent": (
        "PatchIntent",
        {
            "intent_id": STR,
            "operation": {"enum": ["insert", "replace", "delete", "move", "rename"]},
            "target_node": STR,
            "payload_digest": DIGEST,
            "reversible": BOOL,
        },
        ["intent_id", "operation", "target_node", "payload_digest", "reversible"],
    ),
    "transformation-plan": (
        "TransformationPlan",
        {
            "plan_id": STR,
            "passes": STRS,
            "intent_refs": STRS,
            "conflicts": STRS,
            "plan_digest": DIGEST,
        },
        ["plan_id", "passes", "intent_refs", "plan_digest"],
    ),
    "transformation-transaction": (
        "TransformationTransaction",
        {
            "transaction_id": STR,
            "state": {"enum": ["open", "applied", "rolled-back", "committed"]},
            "applied_intents": STRS,
            "rollback_token": STR,
            "workspace_digest_before": DIGEST,
            "workspace_digest_after": {"type": ["string", "null"], "pattern": "^[a-f0-9]{64}$"},
        },
        ["transaction_id", "state", "applied_intents", "rollback_token", "workspace_digest_before"],
    ),
    "verification-obligation": (
        "VerificationObligation",
        {
            "obligation_id": STR,
            "postcondition": STR,
            "checked_by": {"enum": ["compile", "test", "differential", "static", "not-checked"]},
            "result": {"enum": ["pass", "fail", "not-run", "inconclusive"]},
        },
        ["obligation_id", "postcondition", "checked_by", "result"],
    ),
    "agent-repair-proposal": (
        "AgentRepairProposal",
        {
            "proposal_id": STR,
            "agent_id": STR,
            "diff_digest": DIGEST,
            "touches_tests": BOOL,
            "touches_golden": BOOL,
            "touches_gate": BOOL,
            "human_reviewed": BOOL,
        },
        ["proposal_id", "agent_id", "diff_digest", "touches_tests", "touches_golden", "touches_gate", "human_reviewed"],
    ),
    "transformation-certificate": (
        "TransformationCertificate",
        {
            "status": {"enum": STATUSES},
            "plan_id": STR,
            "obligation_refs": STRS,
            "loss_summary": STRS,
            "issued_at": INSTANT,
            "expires_at": INSTANT,
        },
        ["status", "plan_id", "obligation_refs", "issued_at", "expires_at"],
    ),
    # -- Batch 05 ---------------------------------------------------------
    "target-profile": (
        "TargetProfile",
        {
            "profile_id": STR,
            "language": STR,
            "language_version": STR,
            "framework": STR,
            "framework_version": STR,
            "build_tool": STR,
            "platform_constraints": STRS,
        },
        ["profile_id", "language", "language_version", "build_tool"],
    ),
    "backend-plugin-manifest": (
        "BackendPluginManifest",
        {
            "plugin_id": STR,
            "plugin_version": STR,
            "supported_profiles": STRS,
            "contract_digest": DIGEST,
            "capabilities": STRS,
        },
        ["plugin_id", "plugin_version", "supported_profiles", "contract_digest"],
    ),
    "target-typed-ir": (
        "TargetTypedIR",
        {
            "node_id": STR,
            "target_kind": STR,
            "type_ref": STR,
            "idiom": STR,
            "shim_required": BOOL,
        },
        ["node_id", "target_kind", "type_ref", "shim_required"],
    ),
    "target-construction-intent": (
        "TargetConstructionIntent",
        {
            "intent_id": STR,
            "construct": STR,
            "profile_id": STR,
            "source_node_refs": STRS,
            "manual_region": BOOL,
        },
        ["intent_id", "construct", "profile_id", "source_node_refs", "manual_region"],
    ),
    "generation-plan": (
        "GenerationPlan",
        {
            "plan_id": STR,
            "profile_id": STR,
            "passes": STRS,
            "intent_refs": STRS,
            "plan_digest": DIGEST,
        },
        ["plan_id", "profile_id", "passes", "intent_refs", "plan_digest"],
    ),
    "generated-project-manifest": (
        "GeneratedProjectManifest",
        {
            "project_id": STR,
            "profile_id": STR,
            "file_count": INT,
            "manual_region_count": INT,
            "build_status": {"enum": ["not-run", "pass", "fail"]},
            "test_status": {"enum": ["not-run", "pass", "fail"]},
            "project_digest": DIGEST,
        },
        ["project_id", "profile_id", "file_count", "manual_region_count", "build_status", "test_status", "project_digest"],
    ),
    "source-target-map": (
        "SourceTargetMap",
        {
            "source_node": STR,
            "target_node": STR,
            "mapping_kind": {"enum": ["one-to-one", "one-to-many", "many-to-one", "synthesised", "dropped"]},
            "lossless": BOOL,
        },
        ["source_node", "target_node", "mapping_kind", "lossless"],
    ),
    "generation-certificate": (
        "GenerationCertificate",
        {
            "status": {"enum": STATUSES},
            "project_id": STR,
            "build_evidence_ref": STR,
            "test_evidence_ref": STR,
            "manual_regions_preserved": BOOL,
            "issued_at": INSTANT,
            "expires_at": INSTANT,
        },
        ["status", "project_id", "manual_regions_preserved", "issued_at", "expires_at"],
    ),
    # -- shared -----------------------------------------------------------
    "evidence-ref": (
        "EvidenceRef",
        {
            "evidence_id": STR,
            "digest": DIGEST,
            "producer": STR,
            "created_at": INSTANT,
            "trust_level": {"enum": TRUST_LEVELS},
            "scope": STR,
            "expires_at": {"type": ["string", "null"], "format": "date-time"},
        },
        ["evidence_id", "digest", "producer", "created_at", "trust_level", "scope"],
    ),
}


#: Bespoke policy file stem -> machine-readable rule body.
POLICY_SPECS: dict[str, dict[str, Any]] = {
    "claim-verification-policy": {
        "claim_verification": {
            "unverified_claim_in_battlecard": "forbidden",
            "minimum_confidence_for_public_claim": "corroborated",
            "vendor_marketing_alone_is_sufficient": False,
            "recheck_interval_days": 90,
        }
    },
    "evidence-quality-policy": {
        "evidence_quality": {
            "source_uri_required": True,
            "observed_version_required": True,
            "model_claim_is_evidence": False,
            "conflicting_sources_must_be_registered": True,
        }
    },
    "legal-comparison-policy": {
        "legal_comparison": {
            "named_comparison_requires_review": True,
            "superlatives_without_evidence": "forbidden",
            "retain_source_snapshot": True,
        }
    },
    "scoring-policy": {
        "scoring": {
            "explicit_denominator_required": True,
            "unknown_counts_against_coverage": True,
            "weights_must_be_declared": True,
        }
    },
    "stale-evidence-policy": {
        "stale_evidence": {
            "default_ttl_days": 90,
            "expired_evidence_blocks_publication": True,
            "expiry_triggers_recheck": True,
        }
    },
    "default-access-policy": {
        "access": {
            "least_privilege": True,
            "read_only_by_default": True,
            "cross_tenant": "forbidden",
            "credential_reuse": "forbidden",
        }
    },
    "default-evidence-policy": {
        "evidence_first": {
            "success_requires_execution": True,
            "model_claim_is_evidence": False,
            "unknown_must_be_preserved": True,
            "explicit_denominator_required": True,
        }
    },
    "default-probe-policy": {
        "probe": {
            "production_probes": "forbidden",
            "probe_requires_approval": True,
            "probe_budget_seconds": 900,
            "probe_must_be_reversible": True,
        }
    },
    "default-prediction-policy": {
        "prediction": {
            "interval_required": True,
            "minimum_calibration_samples": 20,
            "uncalibrated_prediction_is_advisory": True,
            "point_estimate_alone": "forbidden",
        }
    },
    "default-certificate-policy": {
        "certification": {
            "conservative": True,
            "status_only_upgrade": "forbidden",
            "evidence_digest_required": True,
            "holdout_required_for_certified": True,
            "representative_workload_required": True,
        }
    },
    "cache-invalidation-policy": {
        "cache_invalidation": {
            "key_includes_toolchain_version": True,
            "key_includes_source_digest": True,
            "schema_major_change_invalidates": True,
            "partial_hit_must_recompute": True,
        }
    },
    "frontend-selection-policy": {
        "frontend_selection": {
            "explicit_language_version_required": True,
            "fallback_frontend": "forbidden",
            "unsupported_dialect_is_unknown": True,
        }
    },
    "schema-evolution-policy": {
        "schema_evolution": {
            "major_change_requires_migration": True,
            "silent_field_removal": "forbidden",
            "unknown_field_at_boundary": "reject",
        }
    },
    "semantic-level-policy": {
        "semantic_level": {
            "declared_level_required": True,
            "level_upgrade_requires_evidence": True,
            "downstream_may_not_assume_higher_level": True,
        }
    },
    "unknown-handling-policy": {
        "unknown_handling": {
            "unknown_must_be_preserved": True,
            "unknown_may_not_be_guessed": True,
            "unknown_counts_in_denominator": True,
            "opaque_payload_requires_digest": True,
        }
    },
    "conflict-resolution-policy": {
        "conflict_resolution": {
            "overlapping_rewrites": "reject",
            "priority_ties": "reject",
            "resolution_must_be_recorded": True,
        }
    },
    "default-agent-envelope": {
        "agent_boundary": {
            "proposal_only": True,
            "direct_commit": False,
            "self_approval": False,
            "modify_tests": False,
            "modify_golden": False,
            "modify_gate": False,
        }
    },
    "deterministic-runtime-policy": {
        "deterministic_runtime": {
            "stable_ordering_required": True,
            "wallclock_in_output": "forbidden",
            "worker_count_must_not_change_output": True,
            "iteration_ceiling": 64,
        }
    },
    "recipe-supply-chain-policy": {
        "supply_chain": {
            "signature_required": True,
            "unpinned_dependency": "forbidden",
            "provenance_attestation_required": True,
        }
    },
    "verification-policy": {
        "verification": {
            "postcondition_required": True,
            "not_run_is_not_pass": True,
            "inconclusive_blocks_certification": True,
        }
    },
    "default-build-gate-policy": {
        "build_gate": {
            "compile_must_pass": True,
            "test_must_pass": True,
            "warnings_as_findings": True,
            "skipped_test_counts_as_not_run": True,
        }
    },
    "default-manual-region-policy": {
        "manual_region": {
            "regenerate_may_not_overwrite": True,
            "conflict_requires_human": True,
            "region_markers_required": True,
        }
    },
    "default-shim-policy": {
        "shim": {
            "shim_must_be_declared": True,
            "silent_shim": "forbidden",
            "shim_counts_as_limitation": True,
        }
    },
    "default-target-idiom-policy": {
        "target_idiom": {
            "idiom_selection_must_be_declared": True,
            "semantics_outrank_idiom": True,
            "unsupported_idiom_is_limitation": True,
        }
    },
}
