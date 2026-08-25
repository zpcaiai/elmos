from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any, Iterator

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from tooling import integrate_multitenant_task_finops_skills as integration
from tooling import skill_creator_tools


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / integration.SOURCE_RELATIVE_PATH


def walk_refs(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str):
                yield child
            else:
                yield from walk_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_refs(child)


def resolve_internal_pointer(document: Any, pointer: str) -> Any:
    if not pointer.startswith("#/"):
        raise AssertionError(f"only internal references are permitted: {pointer}")
    current = document
    for raw_token in pointer[2:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or token not in current:
            raise AssertionError(f"unresolved reference: {pointer}")
        current = current[token]
    return current


class MultitenantTaskFinopsSourceContractTests(unittest.TestCase):
    def test_all_schema_examples_validate_under_draft_2020_12(self) -> None:
        schemas = sorted((SOURCE_ROOT / "schemas").glob("*.schema.json"))
        examples = sorted((SOURCE_ROOT / "examples").glob("*.json"))
        self.assertEqual(13, len(schemas))
        self.assertEqual(13, len(examples))

        for schema_path in schemas:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            self.assertEqual(
                "https://json-schema.org/draft/2020-12/schema",
                schema["$schema"],
            )
            example_path = SOURCE_ROOT / "examples" / schema_path.name.removesuffix(
                ".schema.json"
            )
            example_path = example_path.with_suffix(".json")
            self.assertTrue(example_path.is_file(), example_path)
            example = json.loads(example_path.read_text(encoding="utf-8"))
            errors = list(
                Draft202012Validator(
                    schema,
                    format_checker=FormatChecker(),
                ).iter_errors(example)
            )
            self.assertEqual([], errors, f"{example_path}: {errors}")

    def test_openapi_asyncapi_and_configs_are_well_formed(self) -> None:
        openapi = yaml.safe_load((SOURCE_ROOT / "api/openapi.yaml").read_text(encoding="utf-8"))
        asyncapi = yaml.safe_load(
            (SOURCE_ROOT / "events/asyncapi.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual("3.1.0", openapi["openapi"])
        self.assertEqual("2.6.0", asyncapi["asyncapi"])
        self.assertGreaterEqual(len(openapi["paths"]), 10)
        self.assertGreaterEqual(len(asyncapi["channels"]), 7)

        operation_ids = {
            operation["operationId"]
            for path_item in openapi["paths"].values()
            if isinstance(path_item, dict)
            for operation in path_item.values()
            if isinstance(operation, dict) and "operationId" in operation
        }
        self.assertTrue(
            {
                "createTask",
                "pauseTask",
                "resumeTask",
                "cancelTask",
                "getTaskFinancialSummary",
            }.issubset(operation_ids)
        )
        for document in (openapi, asyncapi):
            for pointer in walk_refs(document):
                resolve_internal_pointer(document, pointer)

        configs = sorted((SOURCE_ROOT / "config").glob("*.yaml"))
        self.assertEqual(5, len(configs))
        for config in configs:
            self.assertIsInstance(yaml.safe_load(config.read_text(encoding="utf-8")), dict)

    def test_normalized_dual_root_skills_pass_repository_validator(self) -> None:
        for install_root in integration.INSTALL_ROOTS:
            for _skill_id, skill_name in integration.EXPECTED_SKILLS:
                skill_root = REPOSITORY_ROOT / install_root / skill_name
                valid, message = skill_creator_tools.validate_skill(skill_root)
                self.assertTrue(valid, f"{skill_root}: {message}")
                interface_path = skill_root / "agents/openai.yaml"
                interface = yaml.safe_load(interface_path.read_text(encoding="utf-8"))
                prompt = interface["interface"]["default_prompt"]
                self.assertIn(f"${skill_name}", prompt)
                short = interface["interface"]["short_description"]
                self.assertGreaterEqual(len(short), 25)
                self.assertLessEqual(len(short), 64)

    def test_source_risks_fail_closed_and_reference_sql_is_not_applied(self) -> None:
        register = json.loads(
            (REPOSITORY_ROOT / integration.SOURCE_RISK_REGISTER_RELATIVE_PATH).read_text(
                encoding="utf-8"
            )
        )
        installed = json.loads(
            (REPOSITORY_ROOT / integration.INSTALLED_MANIFEST_RELATIVE_PATH).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("BLOCKED", register["adoption_gate"])
        self.assertEqual(11, register["open_zero_tolerance_findings"])
        self.assertEqual(11, register["finding_count"])
        self.assertTrue(all(item["status"] == "OPEN" for item in register["findings"]))
        self.assertTrue(all(item["severity"] == "CRITICAL" for item in register["findings"]))
        for item in register["findings"]:
            self.assertTrue(item["source_locations"])
            for relative in item["source_locations"]:
                self.assertTrue((SOURCE_ROOT / relative).is_file(), f"missing source: {relative}")
        self.assertEqual(
            {
                "archive_digest_meaning": "BYTE_IDENTITY_ONLY",
                "license": "ABSENT",
                "provenance_attestation": "ABSENT",
                "sbom": "ABSENT",
                "signature": "ABSENT",
            },
            register["supply_chain"],
        )
        self.assertEqual("NOT_APPLIED", installed["reference_material_application_status"])
        self.assertEqual("NOT_RUN", installed["external_evidence_status"])
        self.assertEqual("NOT_CERTIFIED", installed["certification_status"])


if __name__ == "__main__":
    unittest.main()
