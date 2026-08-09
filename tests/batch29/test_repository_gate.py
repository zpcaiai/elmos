from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = ROOT / "scripts" / "batch29" / "run_repository_gate.py"
CAMPAIGN_SCHEMA = (
    ROOT / "schemas" / "batch29" / "repository-capability-campaign.schema.json"
)
RESULT_SCHEMA = ROOT / "schemas" / "batch29" / "repository-gate-result.schema.json"
MAKEFILE = ROOT / "Makefile.batch29"
QUALITY_GATES = ROOT / "docs" / "batch29" / "QUALITY_GATES.md"


def load_gate():
    spec = importlib.util.spec_from_file_location("batch29_repository_gate", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GATE = load_gate()


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def artifact_references(campaign: dict[str, Any]):
    for route in campaign["routes"]:
        for workload in route["workloads"]:
            yield workload["source_inventory"]["snapshot"]
            for stage in (
                workload["source_baseline"]["build"],
                workload["source_baseline"]["test"],
                workload["classification"]["execution"],
                workload["conversion"]["execution"],
                workload["target_repository"]["build"],
                workload["target_repository"]["test"],
            ):
                yield from stage["artifacts"]


class CampaignFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.artifacts = root / "artifacts"
        self.artifacts.mkdir()
        self.campaign_id = "repository-campaign-fixture-001"
        self.command = ["tool", "--locked", "check"]
        self.toolchain = {
            "name": "fixture-toolchain",
            "version": "1.0.0",
            "digest": "sha256:" + "1" * 64,
        }

    def subject(
        self,
        source: str,
        target: str,
        repository_id: str,
        repository_class: str,
        stage: str,
        role: str,
    ) -> dict[str, str]:
        return {
            "campaign_id": self.campaign_id,
            "route_id": f"{source}-to-{target}",
            "source_language": source,
            "target_language": target,
            "repository_id": repository_id,
            "repository_class": repository_class,
            "stage": stage,
            "role": role,
        }

    def artifact(
        self,
        subject: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        role = subject["role"]
        stem = role.lower().replace("_", "-")
        path = (
            self.artifacts
            / subject["route_id"]
            / subject["repository_class"].lower()
            / f"{stem}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": "batch29.repository-evidence.v1",
            "subject": subject,
            "status": "PASSED",
            **payload,
        }
        path.write_text(
            json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        relative = path.relative_to(self.root).as_posix()
        return {
            "artifact_id": (
                f"artifact-{subject['route_id']}-{subject['repository_class'].lower()}-{stem}"
            ),
            "role": role,
            "subject": subject,
            "path": relative,
            "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
            "media_type": "application/json",
        }

    def execution(
        self, artifacts: list[dict[str, Any]], *, test: bool = False
    ) -> dict[str, Any]:
        value: dict[str, Any] = {
            "status": "PASSED",
            "executor": "local-executor",
            "verifier": "independent-verifier",
            "command": self.command,
            "artifacts": artifacts,
        }
        if test:
            value.update(
                {
                    "tests_total": 3,
                    "tests_passed": 3,
                    "tests_failed": 0,
                    "tests_skipped": 0,
                }
            )
        return value

    def workload(
        self, source: str, target: str, repository_class: str
    ) -> dict[str, Any]:
        route_id = f"{source}-to-{target}"
        repository_id = f"{route_id}-{repository_class.lower()}"
        units = 10 if repository_class == "SMALL" else 501
        source_files = [
            {
                "path": f"src/unit_{index:04d}.source",
                "language": source,
                "sha256": "sha256:"
                + hashlib.sha256(f"source-{index}".encode()).hexdigest(),
                "bytes": 100,
            }
            for index in range(units)
        ]
        classification_units = [
            {
                "id": f"unit-{index:04d}",
                "source_path": source_file["path"],
                "verdict": "READY",
            }
            for index, source_file in enumerate(source_files)
        ]
        conversion_units = [
            {
                "id": item["id"],
                "status": "CONVERTED",
                "target_paths": [f"generated/unit_{index:04d}.target"],
            }
            for index, item in enumerate(classification_units)
        ]
        target_files = [
            {
                "path": item["target_paths"][0],
                "sha256": "sha256:"
                + hashlib.sha256(f"target-{index}".encode()).hexdigest(),
                "bytes": 200,
            }
            for index, item in enumerate(conversion_units)
        ]
        tests = [{"id": f"test-{index:02d}", "status": "PASSED"} for index in range(3)]

        def evidence(stage: str, role: str, payload: dict[str, Any]) -> dict[str, Any]:
            return self.artifact(
                self.subject(
                    source,
                    target,
                    repository_id,
                    repository_class,
                    stage,
                    role,
                ),
                payload,
            )

        snapshot = evidence(
            "inventory", "SOURCE_REPOSITORY_SNAPSHOT", {"files": source_files}
        )
        source_build = evidence(
            "source_build",
            "SOURCE_BUILD_LOG",
            {
                "command": self.command,
                "exit_code": 0,
                "toolchain": self.toolchain,
                "source_paths": [item["path"] for item in source_files],
            },
        )
        source_test = evidence(
            "source_test",
            "SOURCE_TEST_LOG",
            {"command": self.command, "tests": tests},
        )
        classification = evidence(
            "classification",
            "CLASSIFICATION_REPORT",
            {"units": classification_units},
        )
        conversion = evidence(
            "conversion", "CONVERSION_REPORT", {"units": conversion_units}
        )
        target_artifact = evidence(
            "target_build",
            "TARGET_REPOSITORY_ARTIFACT",
            {
                "unit_ids": [item["id"] for item in classification_units],
                "files": target_files,
            },
        )
        target_build = evidence(
            "target_build",
            "TARGET_BUILD_LOG",
            {
                "command": self.command,
                "exit_code": 0,
                "toolchain": self.toolchain,
                "built_unit_ids": [item["id"] for item in classification_units],
                "repository_artifact_sha256": target_artifact["sha256"],
            },
        )
        target_test = evidence(
            "target_test",
            "TARGET_TEST_LOG",
            {"command": self.command, "tests": tests},
        )
        return {
            "repository_class": repository_class,
            "repository_id": repository_id,
            "source_inventory": {
                "repository_class": repository_class,
                "file_count": units,
                "source_file_count": units,
                "source_bytes": units * 100,
                "snapshot": snapshot,
            },
            "source_baseline": {
                "build": self.execution([source_build]),
                "test": self.execution([source_test], test=True),
            },
            "classification": {
                "status": "PASSED",
                "total_units": units,
                "classified_units": units,
                "ready_units": units,
                "unsupported_units": 0,
                "skipped_units": 0,
                "failed_units": 0,
                "unknown_units": 0,
                "execution": self.execution([classification]),
            },
            "conversion": {
                "status": "PASSED",
                "total_units": units,
                "attempted_units": units,
                "converted_units": units,
                "unsupported_units": 0,
                "skipped_units": 0,
                "failed_units": 0,
                "execution": self.execution([conversion]),
            },
            "target_repository": {
                "whole_repository": True,
                "included_units": units,
                "excluded_units": 0,
                "build": self.execution([target_build, target_artifact]),
                "test": self.execution([target_test], test=True),
            },
        }

    def campaign(self) -> dict[str, Any]:
        routes = []
        for source in GATE.LANGUAGES:
            for target in GATE.LANGUAGES:
                if source == target:
                    continue
                route_id = f"{source}-to-{target}"
                routes.append(
                    {
                        "route_id": route_id,
                        "source_language": source,
                        "target_language": target,
                        "status": "PASSED",
                        "workloads": [
                            self.workload(source, target, "SMALL"),
                            self.workload(source, target, "MEDIUM"),
                        ],
                    }
                )
        return {
            "schema_version": "batch29.repository-capability-campaign.v1",
            "kind": "elmos.batch29.repository-capability-campaign",
            "campaign_id": self.campaign_id,
            "languages": list(GATE.LANGUAGES),
            "scope": {
                "profile": "repository-wide-v1",
                "repository_classes": ["SMALL", "MEDIUM"],
                "execution_boundary": "LOCAL_ENGINEERING",
            },
            "routes": routes,
            "external_verification_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }


class RepositoryGateTests(unittest.TestCase):
    def evaluate(self, campaign: dict[str, Any], root: Path) -> dict[str, Any]:
        return GATE.evaluate_repository_gate(campaign, root)

    def assert_not_certified(self, result: dict[str, Any]) -> None:
        self.assertEqual("NOT_CERTIFIED", result["certification_decision"])
        self.assertEqual("NOT_RUN", result["external_verification_status"])
        self.assertEqual("READY_FOR_EXTERNAL_GATE", result["maximum_local_decision"])

    def test_schemas_are_valid_json_and_bind_the_exact_matrix(self) -> None:
        campaign_schema = json.loads(CAMPAIGN_SCHEMA.read_text(encoding="utf-8"))
        result_schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(72, campaign_schema["properties"]["routes"]["minItems"])
        self.assertEqual(72, campaign_schema["properties"]["routes"]["maxItems"])
        self.assertEqual(
            list(GATE.LANGUAGES), campaign_schema["properties"]["languages"]["const"]
        )
        self.assertEqual(
            "NOT_CERTIFIED",
            result_schema["properties"]["certification_decision"]["const"],
        )
        self.assertEqual(
            "NOT_RUN",
            result_schema["properties"]["external_verification_status"]["const"],
        )
        try:
            import jsonschema
        except ImportError:
            return
        jsonschema.Draft202012Validator.check_schema(campaign_schema)
        jsonschema.Draft202012Validator.check_schema(result_schema)

    def test_missing_jsonschema_is_explicit_not_run_and_cannot_pass(self) -> None:
        real_import = __import__

        def block_jsonschema(name, *args, **kwargs):
            if name == "jsonschema":
                raise ImportError("blocked by negative test")
            return real_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("builtins.__import__", side_effect=block_jsonschema):
                result = self.evaluate({}, Path(directory))

        self.assertEqual("FAILED", result["gate_status"])
        self.assertEqual("LIMITED", result["decision"])
        self.assertTrue(
            any(
                "jsonschema is required" in failure and "NOT_RUN" in failure
                for failure in result["failures"]
            )
        )

    def test_complete_72_route_small_and_medium_campaign_is_ready_only_externally(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = CampaignFixture(root).campaign()
            result = self.evaluate(campaign, root)

        self.assertEqual([], result["failures"])
        self.assertEqual("PASSED_LOCAL_ENGINEERING", result["gate_status"])
        self.assertEqual("READY_FOR_EXTERNAL_GATE", result["decision"])
        self.assertEqual(72, result["observed_route_count"])
        self.assertEqual(144, result["observed_workload_count"])
        self.assertEqual(72, result["route_status_counts"]["PASSED"])
        self.assertEqual({"SMALL": 72, "MEDIUM": 72}, result["repository_class_counts"])
        self.assertEqual(1_152, result["verified_artifact_reference_count"])
        self.assertEqual(1_152, result["unique_verified_artifact_count"])
        self.assertTrue(result["actor_separation_passed"])
        self.assert_not_certified(result)
        self.assertEqual(canonical_digest(campaign), result["campaign_digest"])
        for field in (
            "campaign_schema_digest",
            "result_schema_digest",
            "gate_implementation_digest",
            "evidence_set_digest",
        ):
            self.assertRegex(result[field], r"^sha256:[0-9a-f]{64}$")
        digest_input = {
            key: value for key, value in result.items() if key != "result_digest"
        }
        self.assertEqual(canonical_digest(digest_input), result["result_digest"])
        try:
            import jsonschema
        except ImportError:
            return
        jsonschema.Draft202012Validator(
            json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
        ).validate(result)

    def test_role_only_eight_file_fixture_can_never_be_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = CampaignFixture(root).campaign()
            legacy = root / "legacy-eight-files"
            legacy.mkdir()
            shared: dict[str, tuple[Path, str]] = {}
            for role in GATE.ARTIFACT_ROLES:
                path = legacy / f"{role.lower()}.txt"
                path.write_text(role + "\n", encoding="utf-8")
                shared[role] = (
                    path,
                    "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            for reference in artifact_references(campaign):
                role = reference["role"]
                path, digest = shared[role]
                reference["artifact_id"] = "artifact-" + role.lower()
                reference["path"] = path.relative_to(root).as_posix()
                reference["sha256"] = digest
                reference["bytes"] = path.stat().st_size
                reference["media_type"] = "text/plain"
            result = self.evaluate(campaign, root)

        self.assertEqual("FAILED", result["gate_status"])
        self.assertEqual("LIMITED", result["decision"])
        self.assertTrue(
            any("application/json" in failure for failure in result["failures"])
        )

    def test_route_and_repository_class_artifact_swaps_fail_subject_binding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = CampaignFixture(root).campaign()
            class_swapped = copy.deepcopy(campaign)

            first = campaign["routes"][0]["workloads"][0]["source_inventory"]
            second = campaign["routes"][1]["workloads"][0]["source_inventory"]
            first["snapshot"], second["snapshot"] = (
                second["snapshot"],
                first["snapshot"],
            )
            route_result = self.evaluate(campaign, root)

            small = class_swapped["routes"][0]["workloads"][0]["source_inventory"]
            medium = class_swapped["routes"][0]["workloads"][1]["source_inventory"]
            small["snapshot"], medium["snapshot"] = (
                medium["snapshot"],
                small["snapshot"],
            )
            class_result = self.evaluate(class_swapped, root)

        self.assertTrue(
            any(
                "does not match its campaign" in item
                for item in route_result["failures"]
            )
        )
        self.assertTrue(
            any(
                "does not match its campaign" in item
                for item in class_result["failures"]
            )
        )
        self.assertEqual("LIMITED", route_result["decision"])
        self.assertEqual("LIMITED", class_result["decision"])

    def test_hard_link_reuse_across_subjects_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = CampaignFixture(root).campaign()
            workload = campaign["routes"][0]["workloads"][0]
            first = workload["source_baseline"]["build"]["artifacts"][0]
            second = workload["source_baseline"]["test"]["artifacts"][0]
            first_path = root / first["path"]
            second_path = root / second["path"]
            second_path.unlink()
            os.link(first_path, second_path)
            second["sha256"] = first["sha256"]
            second["bytes"] = first["bytes"]
            result = self.evaluate(campaign, root)

        self.assertEqual("FAILED", result["gate_status"])
        self.assertTrue(any("hard-link reuse" in item for item in result["failures"]))

    def test_self_reported_counts_must_match_raw_evidence_detail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = CampaignFixture(root).campaign()
            workload = campaign["routes"][0]["workloads"][0]
            workload["source_inventory"]["file_count"] -= 1
            workload["classification"]["total_units"] -= 1
            workload["conversion"]["converted_units"] -= 1
            result = self.evaluate(campaign, root)

        self.assertEqual("FAILED", result["gate_status"])
        self.assertTrue(
            any("raw inventory derives" in item for item in result["failures"])
        )
        self.assertTrue(
            any("raw evidence derives" in item for item in result["failures"])
        )

    def test_makefile_wires_structural_check_and_missing_campaign_fails_closed(
        self,
    ) -> None:
        makefile = MAKEFILE.read_text(encoding="utf-8")
        quality_gates = QUALITY_GATES.read_text(encoding="utf-8")
        self.assertIn("b29-repository-contract-check:", makefile)
        self.assertIn("b29-skills-test: b29-repository-contract-check", makefile)
        self.assertIn("b29-repository-gate:", makefile)
        self.assertIn(
            "Gate R29-H — Small/medium whole-repository matrix", quality_gates
        )

        dry_run = subprocess.run(
            [
                "make",
                "--dry-run",
                "-f",
                str(MAKEFILE),
                "b29-repository-contract-check",
                "BATCH29_PYTHON=python3",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, dry_run.returncode, dry_run.stdout + dry_run.stderr)

        absent = subprocess.run(
            [
                "make",
                "-f",
                str(MAKEFILE),
                "b29-repository-gate",
                "B29_REPOSITORY_CAMPAIGN=",
                "BATCH29_PYTHON=python3",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, absent.returncode)
        self.assertIn("NOT_RUN / NOT_CERTIFIED", absent.stdout + absent.stderr)

    def test_missing_or_not_run_direction_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = CampaignFixture(root)
            campaign = fixture.campaign()
            not_run = copy.deepcopy(campaign)
            not_run["routes"][0]["status"] = "NOT_RUN"
            not_run_result = self.evaluate(not_run, root)

            missing = copy.deepcopy(campaign)
            missing["routes"].pop()
            missing_result = self.evaluate(missing, root)

        self.assertEqual("FAILED", not_run_result["gate_status"])
        self.assertEqual("LIMITED", not_run_result["decision"])
        self.assertEqual(1, not_run_result["route_status_counts"]["NOT_RUN"])
        self.assertTrue(
            any("status is NOT_RUN" in item for item in not_run_result["failures"])
        )
        self.assertEqual("FAILED", missing_result["gate_status"])
        self.assertEqual(71, missing_result["observed_route_count"])
        self.assertTrue(
            any("missing directed pairs" in item for item in missing_result["failures"])
        )
        self.assert_not_certified(not_run_result)
        self.assert_not_certified(missing_result)

    def test_incomplete_classification_and_unsupported_units_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = CampaignFixture(root).campaign()
            classification = campaign["routes"][0]["workloads"][0]["classification"]
            classification["ready_units"] -= 1
            classification["unsupported_units"] = 1
            result = self.evaluate(campaign, root)

        self.assertEqual("FAILED", result["gate_status"])
        self.assertTrue(
            any("does not mark every unit ready" in item for item in result["failures"])
        )
        self.assertTrue(
            any("unsupported_units must be zero" in item for item in result["failures"])
        )
        self.assert_not_certified(result)

    def test_source_and_target_tests_require_zero_skips_and_whole_repository(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = CampaignFixture(root).campaign()
            workload = campaign["routes"][0]["workloads"][0]
            source_test = workload["source_baseline"]["test"]
            source_test["tests_passed"] = 2
            source_test["tests_skipped"] = 1
            target = workload["target_repository"]
            target["whole_repository"] = False
            target["excluded_units"] = 1
            result = self.evaluate(campaign, root)

        self.assertEqual("FAILED", result["gate_status"])
        self.assertTrue(
            any("tests_skipped must be zero" in item for item in result["failures"])
        )
        self.assertTrue(
            any("whole_repository must be true" in item for item in result["failures"])
        )
        self.assertTrue(
            any("excluded_units must be zero" in item for item in result["failures"])
        )

    def test_digest_tampering_and_path_escape_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = CampaignFixture(root)
            campaign = fixture.campaign()
            bad = campaign["routes"][0]["workloads"][0]["source_inventory"]["snapshot"]
            bad_path = root / bad["path"]
            bad_path.write_bytes(bad_path.read_bytes() + b" ")
            tampered = self.evaluate(campaign, root)

            escaped_campaign = fixture.campaign()
            escaped_campaign["routes"][0]["workloads"][0]["source_inventory"][
                "snapshot"
            ]["path"] = "../outside.txt"
            escaped = self.evaluate(escaped_campaign, root)

        self.assertTrue(any("mismatch" in item for item in tampered["failures"]))
        self.assertTrue(
            any("escapes or aliases" in item for item in escaped["failures"])
        )
        self.assertEqual("LIMITED", tampered["decision"])
        self.assertEqual("LIMITED", escaped["decision"])

    def test_executor_and_verifier_roles_are_campaign_wide_disjoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = CampaignFixture(root).campaign()
            execution = campaign["routes"][0]["workloads"][0]["source_baseline"][
                "build"
            ]
            execution["verifier"] = "local-executor"
            result = self.evaluate(campaign, root)

        self.assertEqual("FAILED", result["gate_status"])
        self.assertFalse(result["actor_separation_passed"])
        self.assertTrue(
            any("executor and verifier" in item for item in result["failures"])
        )
        self.assertTrue(any("role sets overlap" in item for item in result["failures"]))

    def test_repository_size_class_is_derived_from_measured_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = CampaignFixture(root).campaign()
            medium_inventory = campaign["routes"][0]["workloads"][1]["source_inventory"]
            medium_inventory["file_count"] = 500
            medium_inventory["source_file_count"] = 500
            medium_inventory["source_bytes"] = 8 * 1024 * 1024
            result = self.evaluate(campaign, root)

        self.assertEqual("FAILED", result["gate_status"])
        self.assertTrue(
            any("measured inventory is SMALL" in item for item in result["failures"])
        )

    def test_cli_writes_result_and_returns_nonzero_for_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = CampaignFixture(root).campaign()
            campaign_path = root / "campaign.json"
            output = root / "gate-result.json"
            campaign_path.write_text(json.dumps(campaign), encoding="utf-8")
            passed = subprocess.run(
                [
                    sys.executable,
                    str(GATE_PATH),
                    str(campaign_path),
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, passed.returncode, passed.stdout + passed.stderr)
            self.assertEqual(
                "READY_FOR_EXTERNAL_GATE",
                json.loads(output.read_text(encoding="utf-8"))["decision"],
            )

            campaign["routes"][0]["status"] = "NOT_RUN"
            campaign_path.write_text(json.dumps(campaign), encoding="utf-8")
            rejected = subprocess.run(
                [sys.executable, str(GATE_PATH), str(campaign_path)],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(1, rejected.returncode)
        self.assertEqual("LIMITED", json.loads(rejected.stdout)["decision"])


if __name__ == "__main__":
    unittest.main()
