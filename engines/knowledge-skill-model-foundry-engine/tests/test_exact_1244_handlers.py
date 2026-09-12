"""Every HOST_ROUTE_BOUND skill has one unique exact compiled handler."""

from __future__ import annotations

import unittest

from elmos_foundry.canonical import canonical_digest
from elmos_foundry.domain import TenantScope
from elmos_foundry.exact_skills.compiler import ExactSkillError
from elmos_foundry.exact_skills.registry import (
    EXPECTED_EXACT_SKILLS,
    get_exact_handler,
    load_exact_handlers,
    run_exact_skill,
)
from elmos_foundry.exact_skills.tool_runtime import EXPECTED_TOOL_IDS, load_tool_runtime
from elmos_foundry.native_semantics import NativeSemanticError, load_native_programs


class Exact1244HandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.programs = load_native_programs()
        cls.handlers = load_exact_handlers()
        cls.tools = load_tool_runtime()
        cls.scope = TenantScope(tenant_id="tenant-exact", project_id="project-foundry")

    def test_inventory_is_exact(self) -> None:
        self.assertEqual(len(self.programs), EXPECTED_EXACT_SKILLS)
        self.assertEqual(len(self.handlers), EXPECTED_EXACT_SKILLS)
        self.assertEqual(set(self.handlers), set(self.programs))
        catalog_tools = {
            str(tool)
            for program in self.programs.values()
            for stage in program.stages
            for tool in stage.get("tools", ())
        }
        self.assertEqual(catalog_tools, set(EXPECTED_TOOL_IDS))
        self.assertEqual(set(self.tools), catalog_tools)
        self.assertEqual(len(self.tools), 183)

    def test_handler_identities_are_unique(self) -> None:
        identities = {
            (
                handler.__module__,
                handler.__qualname__,
                getattr(handler, "handler_id"),
                getattr(handler, "program_digest"),
            )
            for handler in self.handlers.values()
        }
        self.assertEqual(len(identities), EXPECTED_EXACT_SKILLS)
        ids = {id(handler) for handler in self.handlers.values()}
        self.assertEqual(len(ids), EXPECTED_EXACT_SKILLS)
        for name, handler in self.handlers.items():
            self.assertEqual(getattr(handler, "skill_name"), name)
            self.assertEqual(getattr(handler, "handler_id"), f"native.{name}")
            self.assertEqual(getattr(handler, "program_digest"), self.programs[name].digest)

    def test_tool_callables_are_unique(self) -> None:
        identities = {
            (fn.__module__, fn.__qualname__, getattr(fn, "tool_id"))
            for fn in self.tools.values()
        }
        self.assertEqual(len(identities), len(EXPECTED_TOOL_IDS))

    def test_unknown_skill_fails_closed(self) -> None:
        with self.assertRaises(ExactSkillError):
            get_exact_handler("not-a-foundry-skill")
        with self.assertRaises(ExactSkillError):
            run_exact_skill("not-a-foundry-skill", {})

    def test_cross_skill_invocation_fails_closed(self) -> None:
        cobol = get_exact_handler("cobol-copybook-data-model-migration")
        with self.assertRaisesRegex(ExactSkillError, "cannot execute foreign skill"):
            cobol("android-compose-adapter", {}, self.scope, "inv-cross")

    def test_same_payload_two_skills_differ(self) -> None:
        payload = {"text": "shared-corpus", "sql": "SELECT IFNULL(a, 0) FROM `t`"}
        left = run_exact_skill("cobol-copybook-data-model-migration", payload, self.scope, "inv-a")
        right = run_exact_skill("android-compose-adapter", payload, self.scope, "inv-a")
        self.assertEqual(left["status"], "SUCCEEDED")
        self.assertEqual(right["status"], "SUCCEEDED")
        self.assertNotEqual(left["output_digest"], right["output_digest"])
        self.assertNotEqual(left["handler_id"], right["handler_id"])
        self.assertNotEqual(left["program_digest"], right["program_digest"])
        self.assertTrue(left["exact"] and right["exact"])
        self.assertFalse(left["llm_required"] or right["llm_required"])

    def test_input_dependence_and_replay(self) -> None:
        skill = "sql-dialect-parser-and-semantic-ir"
        left_payload = {"sql": "SELECT IFNULL(a, 0) FROM `t`", "source_dialect": "mysql", "target_dialect": "postgresql"}
        right_payload = {"sql": "SELECT NOW() FROM `u`", "source_dialect": "mysql", "target_dialect": "postgresql"}
        left = run_exact_skill(skill, left_payload, self.scope, "inv-sql")
        right = run_exact_skill(skill, right_payload, self.scope, "inv-sql")
        again = run_exact_skill(skill, left_payload, self.scope, "inv-sql")
        self.assertEqual(left["status"], "SUCCEEDED")
        self.assertEqual(right["status"], "SUCCEEDED")
        self.assertNotEqual(left["output_digest"], right["output_digest"])
        self.assertEqual(left["output_digest"], again["output_digest"])
        self.assertIn("COALESCE", str(left["artifacts"].get("transpiled_sql") or left["artifacts"].get("sql")))
        self.assertIn("CURRENT_TIMESTAMP", str(right["artifacts"].get("transpiled_sql") or right["artifacts"].get("sql")))

    def test_invalid_source_fails_closed(self) -> None:
        result = run_exact_skill(
            "android-compose-adapter",
            {"source_code": "def broken("},
            self.scope,
            "inv-bad-src",
        )
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("invalid source_code", result["error"] or "")

    def test_sample_traces_validate(self) -> None:
        samples = [
            "a2a-agent-discovery-messaging",
            "abap-language-adapter",
            "airflow-dag-modernization",
            "android-compose-adapter",
            "cobol-copybook-data-model-migration",
            "spring-security-oauth2-oidc-saml",
            "sql-dialect-parser-and-semantic-ir",
        ]
        for name in samples:
            program = self.programs[name]
            result = run_exact_skill(name, {"probe": name}, self.scope, f"inv-{name[:12]}")
            self.assertEqual(result["status"], "SUCCEEDED", result.get("error"))
            program.validate_result(
                {"semantic_execution": result["semantic_execution"]},
                request_binding_digest=result["input_digest"],
            )
            for output in program.document["outputs"]:
                self.assertIn(output["name"], result["outputs"])

    def test_all_1244_execute_and_validate(self) -> None:
        failed: list[str] = []
        foreign = 0
        for name, program in self.programs.items():
            result = run_exact_skill(name, {"catalog": name}, self.scope, f"inv-{name[:20]}")
            if result.get("status") != "SUCCEEDED":
                failed.append(f"{name}:{result.get('error')}")
                continue
            try:
                program.validate_result(
                    {"semantic_execution": result["semantic_execution"]},
                    request_binding_digest=result["input_digest"],
                )
            except NativeSemanticError as exc:
                failed.append(f"{name}:trace:{exc}")
                continue
            if result.get("handler_id") != program.handler_id:
                foreign += 1
        self.assertEqual(foreign, 0)
        self.assertEqual(failed, [])


class ExactBindingDigestTests(unittest.TestCase):
    def test_broker_binding_override_is_honored(self) -> None:
        program = load_native_programs()["cobol-copybook-data-model-migration"]
        binding = canonical_digest({"request": "broker-binding"})
        result = run_exact_skill(
            program.skill_name,
            {"source": "copybook"},
            TenantScope(tenant_id="tenant-b", project_id="project-b"),
            "inv-bind",
            request_binding_digest=binding,
        )
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(result["semantic_execution"]["request_binding_digest"], binding)
        program.validate_result(
            {"semantic_execution": result["semantic_execution"]},
            request_binding_digest=binding,
        )


if __name__ == "__main__":
    unittest.main()
