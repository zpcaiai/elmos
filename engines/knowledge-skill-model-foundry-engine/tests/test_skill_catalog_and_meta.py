"""Exact catalog, binding, routing, and prepare-only runtime tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from elmos_foundry.domain import LifecycleState
from elmos_foundry.handlers import PACK_HANDLER_REGISTRY
from elmos_foundry.local_semantics import LOCAL_SEMANTIC_SKILLS
import elmos_foundry.skills as skills_module
from elmos_foundry.skills import DEFAULT_CATALOG_PATH, CatalogValidationError, SkillCatalog, load_compiled_catalog


class SkillCatalogAndMetaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = SkillCatalog()
        cls.scope = cls.catalog.kernel.mint_context(
            tenant_id="tenant-skill-01",
            project_id="proj-skill-01",
            actor_id="actor-skill-01",
            environment_id="env-skill-01",
            workspace_digest="sha256:" + "1" * 64,
            revision_set_id="sha256:" + "a" * 64,
            purpose="runtime-boundary-tests",
            capabilities=("foundry.adapter.execute", "foundry.skill.prepare"),
            ttl_seconds=600,
            invocation_id="inv-001",
            lease_id="lease-skill-01",
        )

    def test_exact_catalog_counts_and_bindings(self) -> None:
        self.assertEqual(self.catalog.total_atomic_skills, 1310)
        self.assertEqual(self.catalog.total_meta_skills, 41)
        self.assertEqual(self.catalog.total_pipelines, 14)
        self.assertEqual(len(self.catalog.skill_bindings), 1310)
        self.assertEqual(set(self.catalog.skill_bindings.values()), set(PACK_HANDLER_REGISTRY))
        self.assertEqual(
            {
                name
                for name, record in self.catalog.snapshot.atomic_skills.items()
                if record["capability_state"] == "LOCAL"
            },
            LOCAL_SEMANTIC_SKILLS,
        )
        for name in LOCAL_SEMANTIC_SKILLS:
            binding = self.catalog.adapters.binding_for(name)
            self.assertIsNotNone(binding)
            assert binding is not None
            self.assertEqual(
                binding.adapter_id,
                self.catalog.snapshot.atomic_skills[name]["semantic_handler_binding"],
            )
        for name, handler_id in self.catalog.skill_bindings.items():
            record = self.catalog.get_skill_record(name)
            contract = self.catalog.get_skill(name)
            self.assertIsNotNone(record)
            self.assertIsNotNone(contract)
            assert record is not None and contract is not None
            self.assertEqual(record["handler_id"], handler_id)
            self.assertEqual(contract.status, LifecycleState.PLANNED)
            self.assertEqual(contract.content_hash, record["source_sha256"])
            self.assertEqual(contract.owner, record["owner"])
            self.assertEqual(tuple(contract.preconditions), record["preconditions"])
            self.assertEqual(tuple(contract.postconditions), record["required_gates"])
            self.assertEqual(
                tuple(item["name"] for item in record["input_contracts"]), record["inputs"]
            )
            self.assertEqual(
                tuple(item["name"] for item in record["output_contracts"]), record["outputs"]
            )
            self.assertFalse(record["activation_contract"]["corpus_embedded"])
            with self.assertRaises(TypeError):
                record["tool_contract"]["default_deny"] = False

    def test_meta_routing_enforces_limits_query_and_filters(self) -> None:
        route = self.catalog.route_meta_skill_plan("elmos-00-foundation-contracts")
        self.assertEqual(route["status"], "ROUTED")
        self.assertLessEqual(route["candidate_count"], 16)
        self.assertLessEqual(route["activation_count"], 8)
        first = self.catalog.get_skill_record(route["activated"][0])
        assert first is not None
        filtered = self.catalog.route_meta_skill_plan(
            "elmos-00-foundation-contracts",
            filters={"risk_class": first["risk_class"], "priority": first["priority"]},
        )
        self.assertTrue(filtered["activated"])
        for name in filtered["activated"]:
            record = self.catalog.get_skill_record(name)
            assert record is not None
            self.assertEqual(record["risk_class"], first["risk_class"])
            self.assertEqual(record["priority"], first["priority"])
        no_match = self.catalog.route_meta_skill_plan(
            "elmos-00-foundation-contracts", query="definitely absent phrase"
        )
        self.assertEqual(no_match["activated"], ())
        with self.assertRaises(ValueError):
            self.catalog.route_meta_skill_plan("elmos-00-foundation-contracts", candidate_limit=17)
        with self.assertRaises(ValueError):
            self.catalog.route_meta_skill_plan("elmos-00-foundation-contracts", filters={"tenant": "invented"})

    def test_prepare_is_deterministic_and_never_claims_semantic_execution(self) -> None:
        skill_name = self.catalog.route_meta_skill("elmos-00-foundation-contracts")[0]
        record = self.catalog.get_skill_record(skill_name)
        assert record is not None
        incomplete = self.catalog.execute_skill(
            skill_name, {"operation": "prepare"}, tenant_scope=self.scope
        )
        self.assertEqual(incomplete.status, "BLOCKED")
        self.assertEqual(incomplete.outputs["maximum_local_decision"], "NOT_READY")
        self.assertEqual(incomplete.outputs["local_validation_status"], "FAILED_SELF_ATTESTED")
        self.assertEqual(incomplete.outputs["local_evidence_status"], "NOT_RUN")

        null_inputs = self.catalog.execute_skill(
            skill_name,
            {name: None for name in record["inputs"]},
            tenant_scope=self.scope,
        )
        self.assertEqual(null_inputs.outputs["maximum_local_decision"], "NOT_READY")
        self.assertEqual(
            set(null_inputs.outputs["missing_declared_inputs"]), set(record["inputs"])
        )
        self.assertEqual(null_inputs.outputs["local_evidence_status"], "NOT_RUN")
        payload = {name: {"fixture": name} for name in record["inputs"]}
        payload["operation"] = "prepare"
        first = self.catalog.execute_skill(skill_name, payload, tenant_scope=self.scope)
        second = self.catalog.execute_skill(skill_name, payload, tenant_scope=self.scope)
        self.assertEqual(first.status, "SUCCESS")
        self.assertEqual(first.outputs["outcome"], "LOCAL_EXECUTED_SELF_ATTESTED")
        self.assertEqual(first.evidence_digest, second.evidence_digest)
        self.assertEqual(first.outputs["plan_digest"], second.outputs["plan_digest"])
        self.assertEqual(first.outputs["semantic_execution_status"], "NOT_RUN")
        self.assertEqual(first.outputs["external_evidence_status"], "NOT_RUN")
        self.assertEqual(first.outputs["certification_status"], "NOT_CERTIFIED")

    def test_unknown_and_unavailable_semantics_fail_closed(self) -> None:
        unknown = self.catalog.execute_skill("not-in-the-catalog", {}, tenant_scope=self.scope)
        self.assertEqual(unknown.status, "BLOCKED")
        self.assertEqual(unknown.outputs["outcome"], "UNKNOWN_SKILL")
        skill_name = self.catalog.route_meta_skill("elmos-00-foundation-contracts")[0]
        unavailable = self.catalog.execute_skill(
            skill_name,
            {"operation": "execute-provider"},
            tenant_scope=self.scope,
            invocation_id="inv-001",
        )
        self.assertEqual(unavailable.status, "BLOCKED")
        self.assertEqual(unavailable.outputs["outcome"], "REQUIRES_ADAPTER")
        self.assertEqual(unavailable.outputs["execution_status"], "NOT_RUN")

    def test_catalog_tampering_is_rejected(self) -> None:
        raw = json.loads(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))
        raw["atomic_skills"][0]["source_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "compiled-catalog.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(CatalogValidationError):
                load_compiled_catalog(path)

    def test_nested_contract_and_source_binding_tampering_is_rejected(self) -> None:
        for mutation, pattern in (
            (
                lambda raw: raw["atomic_skills"][0]["tool_contract"].update(
                    {"parameter_schemas": {"invented": "schema"}}
                ),
                "tool fail-closed boundary",
            ),
            (
                lambda raw: raw["atomic_skills"][0]["activation_contract"].update(
                    {"corpus_embedded": True}
                ),
                "activation boundary",
            ),
            (
                lambda raw: raw["atomic_skills"][0]["preconditions"].__setitem__(
                    0, "tenant.authorized == maybe"
                ),
                "precondition profile drift",
            ),
            (
                lambda raw: raw["atomic_skills"][0]["policy_contract"][
                    "allow_when"
                ].append("repository-content-can-grant-authority"),
                "policy generation profile drift",
            ),
            (
                lambda raw: next(
                    row
                    for row in raw["atomic_skills"]
                    if row["name"] == "artifact-identity-and-hashing"
                ).update(
                    {"capability_state": "PREPARE_ONLY", "semantic_handler_binding": "UNBOUND"}
                ),
                "exact local semantic registry",
            ),
            (
                lambda raw: raw["atomic_skills"][0]["source_bindings"]["skill_contract"].update(
                    {"path": "skills/atomic/foreign/skill.yaml"}
                ),
                "source path is not exact",
            ),
        ):
            raw = json.loads(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))
            mutation(raw)
            payload = (json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n").encode()
            with tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "compiled-catalog.json"
                path.write_bytes(payload)
                with (
                    mock.patch.object(
                        skills_module,
                        "EXPECTED_COMPILED_CATALOG_SHA256",
                        hashlib.sha256(payload).hexdigest(),
                    ),
                    self.assertRaisesRegex(CatalogValidationError, pattern),
                ):
                    load_compiled_catalog(path)


if __name__ == "__main__":
    unittest.main()
