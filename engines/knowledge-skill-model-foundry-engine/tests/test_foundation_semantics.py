"""Behavioral tests for foundation contracts, including authority non-escalation."""

from __future__ import annotations

import copy
from functools import lru_cache
from typing import Any
import unittest

from elmos_foundry.domain import TenantScope
from elmos_foundry.foundation_semantics import build_foundation_handlers, FOUNDATION_SEMANTIC_SKILLS
from elmos_foundry.kernel import ExecutionKernel
from elmos_foundry.skills import load_compiled_catalog


_catalog = lru_cache(maxsize=1)(load_compiled_catalog)

DIGEST = "sha256:" + "c" * 64


def fixture_inputs(skill: str, scope: TenantScope) -> dict[str, Any]:
    version_tuple = {
        "kind": "language",
        "name": "python",
        "version": "3.12.0",
        "environment": "local",
    }
    requirement: dict[str, Any] = {
        "purpose": scope.purpose,
        "acceptance": ["Preserve exact version and rollback identity"],
    }
    architecture: dict[str, Any] = {"owner": "team", "version": "1.0.0", "rollback": DIGEST}
    policy: dict[str, Any] = {"required_gates": ["unit-test"]}
    runtime: dict[str, Any] = {"runtime_version": "3.0.0"}
    if skill == "architecture-decision-record":
        architecture = {
            "id": "adr-001",
            "title": "Durable state",
            "context": "Survive restart",
            "owner": "team",
            "version": "1.0.0",
            "selected": "sqlite",
            "alternatives": [
                {
                    "id": "sqlite",
                    "description": "Embedded durable database",
                    "tradeoffs": ["Single writer"],
                },
                {
                    "id": "memory",
                    "description": "Process-local map",
                    "tradeoffs": ["Restart loses state"],
                },
            ],
            "assumptions": ["Single host"],
            "consequences": ["Transactional state"],
            "exit_conditions": ["Multi-host writer required"],
            "supersedes": None,
            "rollback_digest": DIGEST,
        }
    elif skill == "capability-taxonomy-governance":
        runtime = {
            "version": "1.0.0",
            "capabilities": [
                {
                    "name": "artifact-identity-and-hashing",
                    "domain": "foundation",
                    "boundary": "Hash content",
                    "owner": "team",
                    "risk": "low",
                    "maturity": "LOCAL",
                    "dependencies": [],
                },
                {
                    "name": "typed-skill-contract",
                    "domain": "foundation",
                    "boundary": "Validate contracts",
                    "owner": "team",
                    "risk": "high",
                    "maturity": "LOCAL",
                    "dependencies": ["artifact-identity-and-hashing"],
                },
            ],
        }
    elif skill == "compatibility-matrix-manager":
        target = {**version_tuple, "name": "java", "version": "21.0.0"}
        requirement = {"source": version_tuple, "target": target}
        runtime = {
            "version": "1.0.0",
            "rows": [
                {
                    "source": version_tuple,
                    "target": target,
                    "status": "SUPPORTED",
                    "evidence_digest": DIGEST,
                }
            ],
        }
    elif skill == "tenancy-scope-contract":
        requirement = {
            key: getattr(scope, key)
            for key in (
                "tenant_id",
                "project_id",
                "actor_id",
                "environment_id",
                "workspace_digest",
                "revision_set_id",
                "purpose",
            )
        }
        requirement["resources"] = [
            {
                "id": "root",
                "kind": "platform",
                "parent_id": None,
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
            },
            {
                "id": "repo",
                "kind": "repository",
                "parent_id": "root",
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
            },
        ]
    elif skill == "evidence-contract":
        requirement = {
            "subject_digest": DIGEST,
            "executor": "builder",
            "verifier": "reviewer",
            "obligations": [
                {
                    "id": "negative-test",
                    "kind": "test",
                    "mandatory": True,
                    "corpus": "negative",
                    "replay": ["python", "-m", "unittest"],
                    "artifact_digest": DIGEST,
                }
            ],
        }
    elif skill == "policy-contract":
        requirement = {
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "action": "read",
            "resource": "artifact-one",
            "purpose": scope.purpose,
        }
        policy = {
            "version": "1.0.0",
            "default": "DENY",
            "rules": [
                {
                    "id": "allow-read",
                    "effect": "ALLOW",
                    "match": dict(requirement),
                    "obligations": [],
                }
            ],
        }
    elif skill == "data-usage-consent-contract":
        requirement = {
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "subject_digest": DIGEST,
            "purpose": scope.purpose,
            "uses": {
                key: "ALLOW" if key == "retrieve" else "DENY"
                for key in (
                    "retrieve",
                    "record",
                    "label",
                    "train",
                    "aggregate",
                    "export",
                    "delete",
                    "retain",
                )
            },
            "issued_at": 10,
            "expires_at": 20,
            "retention_until": 30,
            "evaluated_at": 15,
            "revoked": False,
        }
    elif skill == "release-bundle-contract":
        catalog = _catalog()
        source = catalog.atomic_skills["typed-skill-contract"]
        requirement = {
            "version": "1.0.0",
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "components": {
                key: DIGEST
                for key in ("model", "adapter", "knowledge", "toolchain", "policy", "evaluation")
            },
            "skills": [{key: source[key] for key in ("name", "version", "source_sha256")}],
            "rollback_digest": DIGEST,
        }
    else:
        raise ValueError("unknown foundation fixture")
    return {
        "business requirement": requirement,
        "architecture decision": architecture,
        "policy profile": policy,
        "runtime capability inventory": runtime,
    }


class FoundationSemanticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kernel = ExecutionKernel()
        self.scope = self.kernel.mint_context(
            tenant_id="tenant-a",
            project_id="project-a",
            actor_id="actor-a",
            environment_id="local",
            workspace_digest=DIGEST,
            revision_set_id=DIGEST,
            purpose="contract-tests",
            capabilities=("foundry.adapter.execute",),
            ttl_seconds=600,
            invocation_id="invoke-a",
            lease_id="lease-a",
        )
        self.handlers = build_foundation_handlers(_catalog(), None)

    def execute(self, skill: str, values: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.handlers[skill](
            skill, {"inputs": values or fixture_inputs(skill, self.scope)}, self.scope, "invoke-a"
        )
        self.assertEqual(response["status"], "SUCCEEDED")
        primary = dict(response["outputs"]["typed contract"])
        self.assertFalse(primary["effect_authorized"])
        return primary

    def test_eight_exact_handlers_compile_real_contracts(self) -> None:
        self.assertEqual(set(self.handlers), FOUNDATION_SEMANTIC_SKILLS)
        for name in self.handlers:
            with self.subTest(name=name):
                first = self.execute(name)
                self.assertEqual(first, self.execute(name))
                self.assertEqual(first["external_evidence_status"], "NOT_RUN")

    def test_adr_selected_alternative_and_digest(self) -> None:
        name = "architecture-decision-record"
        first = self.execute(name)
        values = fixture_inputs(name, self.scope)
        values["architecture decision"]["context"] = "Restart plus replay"
        self.assertNotEqual(first["adr_digest"], self.execute(name, values)["adr_digest"])
        values["architecture decision"]["selected"] = "unknown"
        with self.assertRaisesRegex(ValueError, "selected"):
            self.execute(name, values)

    def test_taxonomy_unknown_duplicate_boundary_cycle_and_maturity(self) -> None:
        name = "capability-taxonomy-governance"
        expected = ["artifact-identity-and-hashing", "typed-skill-contract"]
        self.assertEqual(self.execute(name)["topological_order"], expected)
        for defect in ("unknown", "boundary", "cycle", "maturity"):
            with self.subTest(defect=defect):
                values = fixture_inputs(name, self.scope)
                rows = values["runtime capability inventory"]["capabilities"]
                if defect == "unknown":
                    rows[0]["name"] = "does-not-exist"
                if defect == "boundary":
                    rows[1]["boundary"] = "  HASH CONTENT  "
                if defect == "cycle":
                    rows[0]["dependencies"] = ["typed-skill-contract"]
                if defect == "maturity":
                    rows[0]["maturity"] = "CERTIFIED"
                with self.assertRaises(ValueError):
                    self.execute(name, values)

    def test_compatibility_is_directional_and_never_verifies_caller_claims(self) -> None:
        name = "compatibility-matrix-manager"
        first = self.execute(name)
        self.assertEqual(first["declared_status"], "SUPPORTED")
        self.assertFalse(first["runtime_compatible"])
        values = fixture_inputs(name, self.scope)
        query = values["business requirement"]
        query["source"], query["target"] = query["target"], query["source"]
        self.assertEqual(self.execute(name, values)["declared_status"], "UNKNOWN")
        query["source"]["version"] = "latest"
        with self.assertRaisesRegex(ValueError, "exact"):
            self.execute(name, values)

    def test_scope_rejects_cross_tenant_and_dangling_tree(self) -> None:
        name = "tenancy-scope-contract"
        for defect in ("tenant", "parent", "actor"):
            values = fixture_inputs(name, self.scope)
            request = values["business requirement"]
            if defect == "tenant":
                request["resources"][1]["tenant_id"] = "other"
            if defect == "parent":
                request["resources"][1]["parent_id"] = "missing"
            if defect == "actor":
                request["actor_id"] = "other"
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                self.execute(name, values)

    def test_compatibility_rejects_mutable_aliases_and_wildcard_components(self) -> None:
        name = "compatibility-matrix-manager"
        for version in ("LATEST", " latest ", "3.x", "3.X", "stable", "main"):
            values = fixture_inputs(name, self.scope)
            values["business requirement"]["source"]["version"] = version
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "exact"):
                self.execute(name, values)

    def test_scope_rejects_nontext_resource_kind(self) -> None:
        name = "tenancy-scope-contract"
        values = fixture_inputs(name, self.scope)
        values["business requirement"]["resources"][0]["kind"] = []
        with self.assertRaises(ValueError):
            self.execute(name, values)

    def test_evidence_replay_preserves_repeated_arguments(self) -> None:
        name = "evidence-contract"
        values = fixture_inputs(name, self.scope)
        argv = ["pytest", "-p", "no:cacheprovider", "-p", "no:warnings"]
        values["business requirement"]["obligations"][0]["replay"] = argv
        self.assertEqual(self.execute(name, values)["contract"]["obligations"][0]["replay"], argv)

    def test_evidence_separation_and_no_fabricated_results(self) -> None:
        name = "evidence-contract"
        self.assertEqual(self.execute(name)["contract"]["obligations"][0]["status"], "NOT_RUN")
        values = fixture_inputs(name, self.scope)
        values["business requirement"]["verifier"] = "builder"
        with self.assertRaisesRegex(ValueError, "differ"):
            self.execute(name, values)
        values = fixture_inputs(name, self.scope)
        values["business requirement"]["obligations"][0]["status"] = "PASS"
        with self.assertRaises(ValueError):
            self.execute(name, values)

    def test_policy_deny_overrides_allow_and_default_deny(self) -> None:
        name = "policy-contract"
        self.assertEqual(self.execute(name)["simulation_decision"], "ALLOW")
        values = fixture_inputs(name, self.scope)
        rule = copy.deepcopy(values["policy profile"]["rules"][0])
        rule.update(id="deny-read", effect="DENY")
        values["policy profile"]["rules"].append(rule)
        self.assertEqual(self.execute(name, values)["simulation_decision"], "DENY")
        values["policy profile"]["rules"] = []
        self.assertEqual(self.execute(name, values)["simulation_decision"], "DENY")

    def test_policy_rejects_unsupported_obligations_and_wildcards(self) -> None:
        name = "policy-contract"
        for defect in ("obligation", "wildcard", "default"):
            values = fixture_inputs(name, self.scope)
            if defect == "obligation":
                values["policy profile"]["rules"][0]["obligations"] = ["export-all"]
            if defect == "wildcard":
                values["policy profile"]["rules"][0]["match"]["resource"] = "*"
            if defect == "default":
                values["policy profile"]["default"] = "ALLOW"
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                self.execute(name, values)

    def test_consent_expiry_revocation_purpose_and_boolean_time(self) -> None:
        name = "data-usage-consent-contract"
        first = self.execute(name)
        self.assertEqual(first["declared_use_decisions"]["retrieve"], "ALLOW")
        self.assertFalse(first["training_authorized"])
        for key, value in (("evaluated_at", 20), ("revoked", True), ("purpose", "different")):
            values = fixture_inputs(name, self.scope)
            values["business requirement"][key] = value
            self.assertEqual(
                set(self.execute(name, values)["declared_use_decisions"].values()), {"DENY"}
            )
        values = fixture_inputs(name, self.scope)
        values["business requirement"]["evaluated_at"] = True
        with self.assertRaises(ValueError):
            self.execute(name, values)

    def test_release_exact_pin_and_content_identity(self) -> None:
        name = "release-bundle-contract"
        first = self.execute(name)
        self.assertFalse(first["published"])
        values = fixture_inputs(name, self.scope)
        values["business requirement"]["components"]["model"] = "sha256:" + "d" * 64
        self.assertNotEqual(first["bundle_digest"], self.execute(name, values)["bundle_digest"])
        values["business requirement"]["skills"][0]["version"] = "latest"
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.execute(name, values)


if __name__ == "__main__":
    unittest.main()
