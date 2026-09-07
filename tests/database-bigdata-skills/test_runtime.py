from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
ENGINE_SOURCE = ROOT / "engines/database-bigdata-engine/src"
if str(ENGINE_SOURCE) not in sys.path:
    sys.path.insert(0, str(ENGINE_SOURCE))

from elmos_database_bigdata import bootstrap, catalog, cli, runtime
from elmos_database_bigdata.canonical import (
    MAX_JSON_BYTES,
    MAX_JSON_DEPTH,
    MAX_JSON_NODES,
    MAX_SAFE_INTEGER,
    CanonicalError,
    canonical_digest,
    canonical_value,
)
from elmos_database_bigdata.catalog import (
    SKILL_CONTRACTS,
    CatalogError,
    load_installed_manifest,
    validate_catalog,
)
from elmos_database_bigdata.contracts import (
    REQUEST_SCHEMA,
    ContractError,
    RuntimeRequest,
    denied_external_capabilities,
)
from elmos_database_bigdata.runtime import (
    SKILL_REGISTRY,
    capability_manifest,
    dispatch_skill,
    execute_skill,
    validate_registry,
)
from elmos_database_bigdata.runtime import (
    RuntimeError as SkillRuntimeError,
)

TASK_ID_PATTERN = re.compile(r"\*\*([A-Z0-9]+-[0-9]{3})\*\*")
EXPECTED_GROUP_COUNTS = {
    "bigdata-core": 22,
    "bigdata-templates": 10,
    "database-intelligence": 13,
    "orchestration": 1,
}


def request(
    skill: str,
    *,
    tenant_id: str = "tenant-a",
    idempotency_key: str = "idempotency-a",
) -> dict[str, object]:
    return {
        "schema_version": REQUEST_SCHEMA,
        "skill": skill,
        "operation": "plan",
        "request_id": "request-a",
        "tenant_id": tenant_id,
        "project_id": "project-a",
        "actor_id": "actor-a",
        "idempotency_key": idempotency_key,
        "inputs": {
            "objective": "Compile a bounded, provider-neutral plan.",
            "output_path": "plans/result.json",
            "artifact_paths": ["artifacts/plan.json", "artifacts/gaps.json"],
            "unknowns": ["exact provider version", "representative workload"],
        },
        "external_capabilities": denied_external_capabilities(),
    }


def source_manifest() -> dict[str, object]:
    path = ROOT / "skills/elmos-database-bigdata-skills-v1.0.0/MANIFEST.json"
    return json.loads(path.read_text(encoding="utf-8"))


def source_task_ids(source_path: Path) -> tuple[str, ...]:
    return tuple(TASK_ID_PATTERN.findall(source_path.read_text(encoding="utf-8")))


class DatabaseBigDataRuntimeTests(unittest.TestCase):
    def test_01_registry_preserves_exact_source_order_groups_and_unique_handlers(
        self,
    ) -> None:
        validate_registry()
        canonical_names = tuple(item["name"] for item in source_manifest()["skills"])
        bindings = list(SKILL_REGISTRY.values())

        self.assertEqual(canonical_names, tuple(SKILL_REGISTRY))
        self.assertEqual(46, len(bindings))
        self.assertEqual(list(range(46)), [binding.ordinal for binding in bindings])
        self.assertEqual(
            EXPECTED_GROUP_COUNTS, Counter(binding.group for binding in bindings)
        )
        self.assertEqual(46, len({binding.handler_id for binding in bindings}))
        self.assertEqual(46, len({id(binding.handler) for binding in bindings}))
        self.assertTrue(
            all(binding.handler_id == binding.handler.__name__ for binding in bindings)
        )

    def test_02_all_554_source_task_ids_have_exact_catalog_coverage(self) -> None:
        records = validate_catalog()
        expected_ids: list[str] = []
        runtime_ids: list[str] = []

        for contract in SKILL_CONTRACTS:
            record = records[contract.name]
            path = ROOT / record["source_path"]
            parsed = source_task_ids(path)
            with self.subTest(skill=contract.name):
                self.assertEqual(contract.task_ids, parsed)
                self.assertEqual(list(parsed), record["source_task_ids"])
            expected_ids.extend(parsed)
            runtime_ids.extend(contract.task_ids)

        self.assertEqual(554, len(expected_ids))
        self.assertEqual(554, len(set(expected_ids)))
        self.assertEqual(expected_ids, runtime_ids)

    def test_03_every_task_ledger_retains_declared_not_run_not_certified(self) -> None:
        seen: list[str] = []
        for binding in SKILL_REGISTRY.values():
            result = execute_skill(request(binding.skill))
            with self.subTest(skill=binding.skill):
                self.assertEqual("BLOCKED", result["state"])
                self.assertEqual("DECLARED_SKILL_PLAN_SKELETON", result["code"])
                self.assertEqual("SKELETON_ONLY", result["planning_state"])
                self.assertEqual(
                    "IDENTITIES_OUTPUTS_AND_EVIDENCE_GAPS_ONLY",
                    result["plan_skeleton_scope"],
                )
                self.assertFalse(result["external_effects_performed"])
                self.assertEqual(
                    "CALLER_ASSERTED_UNVERIFIED", result["context_assurance"]
                )
                self.assertEqual(
                    "DIGEST_BINDING_ONLY_NO_REPLAY_STORE",
                    result["idempotency_semantics"],
                )
                self.assertEqual("DECLARED", result["skill_implementation_state"])
                self.assertEqual(
                    "NOT_RUN", result["repository_handler_runtime_evidence"]
                )
                self.assertEqual("NOT_RUN", result["provider_runtime_evidence"])
                self.assertEqual("NOT_RUN", result["external_evidence_status"])
                self.assertEqual("NOT_CERTIFIED", result["production_certification"])
                self.assertEqual(
                    "BLOCKED_PENDING_EXACT_EVIDENCE",
                    result["decision_policy"]["recommendation_state"],
                )
                self.assertFalse(
                    result["decision_policy"]["constraint_relaxation_performed"]
                )
                self.assertEqual(
                    list(binding.contract.task_ids),
                    [item["task_id"] for item in result["task_ledger"]],
                )
                for task in result["task_ledger"]:
                    self.assertEqual("NOT_RUN", task["planning_state"])
                    self.assertEqual("DECLARED", task["skill_implementation_state"])
                    self.assertEqual("NOT_RUN", task["runtime_evidence"])
                    self.assertEqual("NOT_RUN", task["provider_runtime_evidence"])
                    self.assertEqual("NOT_RUN", task["external_evidence_status"])
                    self.assertEqual("NOT_CERTIFIED", task["production_certification"])
                    seen.append(task["task_id"])
                for artifact in result["artifacts"]:
                    self.assertEqual("DECLARED_OUTPUT", artifact["artifact_state"])
                    self.assertEqual("NOT_GENERATED", artifact["content_state"])
                    self.assertEqual("DECLARED", artifact["skill_implementation_state"])
                    self.assertEqual("NOT_RUN", artifact["runtime_evidence"])
                    self.assertEqual("NOT_RUN", artifact["provider_runtime_evidence"])
                    self.assertEqual("NOT_RUN", artifact["external_evidence_status"])
                    self.assertEqual(
                        "NOT_CERTIFIED", artifact["production_certification"]
                    )

        self.assertEqual(554, len(seen))
        self.assertEqual(554, len(set(seen)))

    def test_04_strict_request_is_deterministic_and_binds_tenant_and_idempotency(
        self,
    ) -> None:
        skill = "elmos-data-requirement-intake"
        document = request(skill)
        first = execute_skill(document)
        second = dispatch_skill(skill, copy.deepcopy(document))
        self.assertEqual(first, second)
        self.assertEqual("tenant-a", first["tenant_id"])
        self.assertEqual("idempotency-a", first["idempotency_key"])
        self.assertEqual(
            first["result_digest"],
            canonical_digest(
                {key: value for key, value in first.items() if key != "result_digest"}
            ),
        )

        for field in (
            "request_id",
            "tenant_id",
            "project_id",
            "actor_id",
            "idempotency_key",
        ):
            changed = request(skill)
            changed[field] = f"changed-{field}"
            changed_result = execute_skill(changed)
            with self.subTest(field=field):
                self.assertEqual(first["input_digest"], changed_result["input_digest"])
                self.assertNotEqual(
                    first["request_binding_digest"],
                    changed_result["request_binding_digest"],
                )
                self.assertNotEqual(
                    first["result_digest"], changed_result["result_digest"]
                )
                self.assertEqual(changed[field], changed_result[field])

    def test_05_unknown_skill_extra_fields_and_dispatch_mismatch_fail_closed(
        self,
    ) -> None:
        unknown = request("elmos-does-not-exist")
        with self.assertRaisesRegex(
            SkillRuntimeError, "unknown database/Big Data Skill"
        ):
            execute_skill(unknown)

        malformed = request("elmos-data-requirement-intake")
        malformed["embedded_command"] = "execute source package script"
        with self.assertRaisesRegex(ContractError, "fields are not exact"):
            execute_skill(malformed)

        non_string_field = request("elmos-data-requirement-intake")
        non_string_field[1] = "ambiguous"
        with self.assertRaisesRegex(ContractError, "field names must be strings"):
            execute_skill(non_string_field)

        with self.assertRaisesRegex(ContractError, "must be identical"):
            dispatch_skill(
                "elmos-workload-profiler", request("elmos-data-requirement-intake")
            )

        for field in (
            "request_id",
            "tenant_id",
            "project_id",
            "actor_id",
            "idempotency_key",
        ):
            for invalid in ("", " ", "path/value", 1, "x" * 129):
                malformed_context = request("elmos-data-requirement-intake")
                malformed_context[field] = invalid
                with (
                    self.subTest(field=field, invalid=invalid),
                    self.assertRaises(ContractError),
                ):
                    execute_skill(malformed_context)

    def test_06_ambiguous_numbers_resource_abuse_and_path_escape_fail_closed(
        self,
    ) -> None:
        skill = "elmos-data-requirement-intake"
        for invalid in (0.0, -0.0, 0.1, 1e-9, float("nan"), float("inf")):
            document = request(skill)
            document["inputs"]["invalid_number"] = invalid
            with (
                self.subTest(invalid=invalid),
                self.assertRaisesRegex(CanonicalError, "floating-point"),
            ):
                execute_skill(document)

        for invalid in (MAX_SAFE_INTEGER + 1, -(MAX_SAFE_INTEGER + 1)):
            document = request(skill)
            document["inputs"]["invalid_integer"] = invalid
            with self.assertRaisesRegex(CanonicalError, "unsafe JSON integer"):
                execute_skill(document)

        too_deep: object = "leaf"
        for _ in range(MAX_JSON_DEPTH + 1):
            too_deep = [too_deep]
        with self.assertRaisesRegex(CanonicalError, "depth limit"):
            canonical_value(too_deep)
        with self.assertRaisesRegex(CanonicalError, "node limit"):
            canonical_value([None] * (MAX_JSON_NODES + 1))

        non_string_input_key = request(skill)
        non_string_input_key["inputs"][1] = "ambiguous"
        with self.assertRaisesRegex(CanonicalError, "keys must be non-empty strings"):
            execute_skill(non_string_input_key)

        for escaped in (
            "../outside.json",
            "/tmp/outside.json",
            "safe/../outside",
            "safe\\outside",
        ):
            document = request(skill)
            document["inputs"]["output_path"] = escaped
            with self.subTest(path=escaped), self.assertRaises(ContractError):
                execute_skill(document)

        exact_path_field = request(skill)
        exact_path_field["inputs"]["path"] = "../outside.json"
        with self.assertRaises(ContractError):
            execute_skill(exact_path_field)

    def test_07_external_capabilities_and_side_effect_operations_fail_closed(
        self,
    ) -> None:
        skill = "elmos-bigdata-project-orchestrator"
        for capability in denied_external_capabilities():
            document = request(skill)
            document["external_capabilities"][capability] = True
            with (
                self.subTest(capability=capability),
                self.assertRaisesRegex(
                    ContractError, "external capabilities are disabled"
                ),
            ):
                execute_skill(document)

        non_boolean = request(skill)
        non_boolean["external_capabilities"]["database"] = 0
        with self.assertRaisesRegex(ContractError, "must be booleans"):
            execute_skill(non_boolean)

        for operation in (
            "execute",
            "deploy",
            "benchmark",
            "chaos",
            "repair",
            "cutover",
            "certification",
        ):
            document = request(skill)
            document["operation"] = operation
            with (
                self.subTest(operation=operation),
                self.assertRaisesRegex(ContractError, "operation must be plan"),
            ):
                execute_skill(document)

    def test_08_capability_manifest_is_exact_deterministic_and_conservative(
        self,
    ) -> None:
        first = capability_manifest()
        second = capability_manifest()
        self.assertEqual(first, second)
        self.assertEqual(46, first["skill_count"])
        self.assertEqual(554, first["stable_task_id_count"])
        self.assertEqual(EXPECTED_GROUP_COUNTS, first["group_counts"])
        self.assertFalse(first["external_effects_declared"])
        self.assertEqual("BOUNDED_PLAN_SKELETON", first["runtime_kind"])
        self.assertEqual("BEST_EFFORT_AST_ALLOWLIST", first["static_safety_validation"])
        self.assertEqual("CALLER_ASSERTED_UNVERIFIED", first["context_assurance"])
        self.assertEqual(
            "DIGEST_BINDING_ONLY_NO_REPLAY_STORE",
            first["idempotency_semantics"],
        )
        self.assertEqual("DECLARED", first["skill_implementation_state"])
        self.assertEqual("NOT_RUN", first["repository_handler_runtime_evidence"])
        self.assertEqual("NOT_RUN", first["provider_runtime_evidence"])
        self.assertEqual("NOT_RUN", first["external_evidence_status"])
        self.assertEqual("NOT_CERTIFIED", first["production_certification"])
        self.assertEqual(
            list(SKILL_REGISTRY), [item["skill"] for item in first["capabilities"]]
        )
        self.assertEqual(
            first["manifest_digest"],
            canonical_digest(
                {key: value for key, value in first.items() if key != "manifest_digest"}
            ),
        )
        for capability in first["capabilities"]:
            self.assertEqual("DECLARED", capability["skill_implementation_state"])
            self.assertEqual("NOT_RUN", capability["runtime_evidence"])
            self.assertEqual("NOT_CERTIFIED", capability["production_certification"])

    def test_09_cli_catalog_and_run_are_machine_readable_invoke_surfaces(self) -> None:
        catalog_stdout = io.StringIO()
        catalog_stderr = io.StringIO()
        with redirect_stdout(catalog_stdout), redirect_stderr(catalog_stderr):
            catalog_status = cli.main(["catalog"])
        self.assertEqual(0, catalog_status)
        self.assertEqual("", catalog_stderr.getvalue())
        catalog_result = json.loads(catalog_stdout.getvalue())
        self.assertEqual(46, catalog_result["skill_count"])
        self.assertEqual("NOT_CERTIFIED", catalog_result["production_certification"])
        self.assertEqual(
            "DIRECT_IMPORT_TRUSTED_CODE_ONLY",
            catalog_result["preimport_integrity_check"],
        )
        self.assertEqual(
            "DIRECT_IMPORT_TRUSTED_CODE_ONLY",
            catalog_result["provenance"]["launch_assurance"],
        )

        document = request("elmos-bigdata-pattern-selector")
        run_stdout = io.StringIO()
        run_stderr = io.StringIO()
        with (
            mock.patch.object(sys, "stdin", io.StringIO(json.dumps(document))),
            redirect_stdout(run_stdout),
            redirect_stderr(run_stderr),
        ):
            run_status = cli.main(["run"])
        self.assertEqual(0, run_status)
        self.assertEqual("", run_stderr.getvalue())
        self.assertEqual(execute_skill(document), json.loads(run_stdout.getvalue()))

        bootstrap_stdout = io.StringIO()
        bootstrap_stderr = io.StringIO()
        with redirect_stdout(bootstrap_stdout), redirect_stderr(bootstrap_stderr):
            bootstrap_status = bootstrap.main(["catalog"])
        self.assertEqual(0, bootstrap_status)
        self.assertEqual("", bootstrap_stderr.getvalue())
        self.assertEqual(catalog_result, json.loads(bootstrap_stdout.getvalue()))

        launcher = ROOT / "engines/database-bigdata-engine/launcher.py"
        unisolated = subprocess.run(
            [sys.executable, "-B", str(launcher), "catalog"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, unisolated.returncode)
        self.assertEqual("", unisolated.stdout)
        self.assertEqual(
            "ISOLATED_LAUNCH_REQUIRED",
            json.loads(unisolated.stderr)["code"],
        )

        launched = subprocess.run(
            [sys.executable, "-I", "-S", "-B", str(launcher), "catalog"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, launched.returncode, launched.stderr)
        self.assertEqual("", launched.stderr)
        launched_result = json.loads(launched.stdout)
        expected_launched = copy.deepcopy(catalog_result)
        expected_launched["preimport_integrity_check"] = (
            "ISOLATED_DIRECT_LAUNCHER_VERIFIED_SOURCE_LOADER"
        )
        expected_launched["provenance"]["launch_assurance"] = (
            "ISOLATED_DIRECT_LAUNCHER_VERIFIED_SOURCE_LOADER"
        )
        expected_launched["manifest_digest"] = canonical_digest(
            {
                key: value
                for key, value in expected_launched.items()
                if key != "manifest_digest"
            }
        )
        self.assertEqual(expected_launched, launched_result)

        with tempfile.TemporaryDirectory() as temporary:
            shadow = Path(temporary) / "hashlib.py"
            shadow.write_text("raise SystemExit(97)\n", encoding="utf-8")
            isolated_environment = dict(os.environ)
            isolated_environment["PYTHONPATH"] = temporary
            shadow_attempt = subprocess.run(
                [sys.executable, "-I", "-S", "-B", str(launcher), "catalog"],
                cwd=temporary,
                env=isolated_environment,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(0, shadow_attempt.returncode, shadow_attempt.stderr)
        self.assertEqual("", shadow_attempt.stderr)
        self.assertEqual(expected_launched, json.loads(shadow_attempt.stdout))
        self.assertFalse(
            any(
                "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}
                for path in (ROOT / "engines/database-bigdata-engine").rglob("*")
            )
        )

    def test_10_cli_rejects_duplicate_keys_floats_and_oversized_input(self) -> None:
        base = json.dumps(request("elmos-data-requirement-intake"))
        documents = (
            base.replace(
                '"tenant_id": "tenant-a"',
                '"tenant_id":"tenant-a","tenant_id":"tenant-b"',
            ),
            base.replace(
                '"inputs": {',
                '"inputs":{"hard_constraints":{"money":"1.00","money":"2.00"},',
            ),
            base.replace('"inputs": {', '"inputs":{"money":1.0000000000000001,'),
            base.replace('"inputs": {', '"inputs":{"huge":' + "9" * 4301 + ","),
            " " * (MAX_JSON_BYTES + 1),
        )
        for raw in documents:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.object(sys, "stdin", io.StringIO(raw)),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                status = cli.main(["run"])
            with self.subTest(prefix=raw[:40]):
                self.assertEqual(2, status)
                self.assertEqual("", stdout.getvalue())
                error = json.loads(stderr.getvalue())
                self.assertEqual("BLOCKED", error["state"])
                self.assertFalse(error["external_effects_performed"])
                self.assertEqual("DECLARED", error["skill_implementation_state"])
                self.assertEqual("NOT_RUN", error["runtime_evidence"])
                self.assertEqual("NOT_CERTIFIED", error["production_certification"])

    def test_11_source_runtime_and_result_provenance_are_digest_bound(
        self,
    ) -> None:
        records = validate_registry()
        for binding in SKILL_REGISTRY.values():
            record = records[binding.skill]
            source_path = ROOT / record["source_path"]
            actual_digest = (
                "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()
            )
            with self.subTest(skill=binding.skill):
                self.assertEqual(actual_digest, record["source_sha256"])
                self.assertEqual(
                    list(binding.contract.task_ids), record["source_task_ids"]
                )
                self.assertEqual(binding.handler_id, record["repository_handler_id"])
                result = execute_skill(request(binding.skill))
                self.assertEqual(
                    actual_digest, result["provenance"]["source_skill_sha256"]
                )
                self.assertEqual(
                    record["repository_handler_file_sha256"],
                    result["provenance"]["repository_handler_file_sha256"],
                )
                self.assertEqual(
                    "LOCAL_BYTE_IDENTITY_ONLY",
                    result["provenance"]["digest_binding_state"],
                )
                self.assertEqual(
                    "DIRECT_IMPORT_TRUSTED_CODE_ONLY",
                    result["provenance"]["launch_assurance"],
                )
                self.assertEqual("ABSENT", result["provenance"]["signature_status"])
                self.assertEqual(
                    "NOT_RUN", result["provenance"]["independent_verification"]
                )

    def test_12_catalog_status_source_or_runtime_digest_drift_fails_closed(
        self,
    ) -> None:
        manifest = load_installed_manifest(ROOT)

        task_drift = copy.deepcopy(manifest)
        task_drift["skills"][0]["source_task_ids"][0] = "DRIFT-001"
        with (
            mock.patch.object(
                catalog, "load_installed_manifest", return_value=task_drift
            ),
            self.assertRaisesRegex(CatalogError, "task IDs differ"),
        ):
            validate_catalog(ROOT)

        digest_drift = copy.deepcopy(manifest)
        digest_drift["skills"][0]["source_sha256"] = "sha256:" + "0" * 64
        with (
            mock.patch.object(
                catalog, "load_installed_manifest", return_value=digest_drift
            ),
            self.assertRaisesRegex(CatalogError, "source digest differs"),
        ):
            validate_catalog(ROOT)

        handler_drift = copy.deepcopy(manifest)
        handler_drift["skills"][0]["repository_handler_file_sha256"] = (
            "sha256:" + "0" * 64
        )
        with (
            mock.patch.object(runtime, "manifest_document", return_value=handler_drift),
            self.assertRaisesRegex(SkillRuntimeError, "handler source digest drifted"),
        ):
            validate_registry()

        for field, raised in (
            ("repository_handler_runtime_evidence", "PASSED"),
            ("whole_skill_implementation_effect", "IMPLEMENTED"),
            ("reference_tool_state", "LOCAL_EXECUTED"),
            ("provider_runtime_evidence", "PASSED"),
            ("external_evidence_status", "PASSED"),
            ("production_certification", "CERTIFIED"),
        ):
            status_drift = copy.deepcopy(manifest)
            status_drift["skills"][0][field] = raised
            with (
                mock.patch.object(
                    catalog, "load_installed_manifest", return_value=status_drift
                ),
                self.assertRaisesRegex(CatalogError, "Skill status drifted"),
            ):
                validate_catalog(ROOT)

        for field, raised in (
            ("skill_implementation_state", "IMPLEMENTED"),
            ("repository_handler_runtime_evidence", "PASSED"),
            ("reference_tool_state", "LOCAL_EXECUTED"),
            ("provider_runtime_evidence", "PASSED"),
            ("external_evidence_status", "PASSED"),
            ("production_certification", "CERTIFIED"),
        ):
            top_status_drift = copy.deepcopy(manifest)
            top_status_drift[field] = raised
            with (
                mock.patch.object(
                    catalog, "load_installed_manifest", return_value=top_status_drift
                ),
                self.assertRaisesRegex(CatalogError, "manifest status drifted"),
            ):
                validate_catalog(ROOT)

        tree_drift = copy.deepcopy(manifest)
        tree_drift["repository_runtime_tree_sha256"] = "sha256:" + "0" * 64
        with (
            mock.patch.object(runtime, "manifest_document", return_value=tree_drift),
            self.assertRaisesRegex(SkillRuntimeError, "runtime tree digest drifted"),
        ):
            validate_registry()

        archive_drift = copy.deepcopy(manifest)
        archive_drift["source_archive_sha256"] = "sha256:" + "0" * 64
        with (
            mock.patch.object(
                catalog, "load_installed_manifest", return_value=archive_drift
            ),
            self.assertRaisesRegex(CatalogError, "source archive digest drifted"),
        ):
            validate_catalog(ROOT)

    def test_13_input_claims_cannot_raise_authoritative_states(self) -> None:
        document = request("elmos-bigdata-evidence-certification")
        document["inputs"].update(
            {
                "skill_implementation_state": "IMPLEMENTED",
                "runtime_evidence": "PASSED",
                "production_certification": "CERTIFIED",
                "context_assurance": "VERIFIED",
                "provenance": "ATTESTED",
            }
        )
        result = execute_skill(document)
        self.assertEqual("BLOCKED", result["state"])
        self.assertEqual("DECLARED", result["skill_implementation_state"])
        self.assertEqual("NOT_RUN", result["repository_handler_runtime_evidence"])
        self.assertEqual("NOT_RUN", result["provider_runtime_evidence"])
        self.assertEqual("NOT_RUN", result["external_evidence_status"])
        self.assertEqual("NOT_CERTIFIED", result["production_certification"])
        self.assertEqual("CALLER_ASSERTED_UNVERIFIED", result["context_assurance"])
        for task in result["task_ledger"]:
            self.assertEqual("NOT_RUN", task["planning_state"])
            self.assertEqual("DECLARED", task["skill_implementation_state"])
            self.assertEqual("NOT_CERTIFIED", task["production_certification"])

    def test_14_installed_manifest_duplicate_keys_fail_closed(self) -> None:
        with mock.patch.object(
            catalog,
            "repository_root",
            return_value=ROOT,
        ):
            raw = (
                '{"skill_implementation_state":"DECLARED",'
                '"skill_implementation_state":"IMPLEMENTED"}'
            )
            with (
                mock.patch.object(Path, "read_bytes", return_value=raw.encode()),
                self.assertRaisesRegex(CatalogError, "duplicate object key"),
            ):
                load_installed_manifest(ROOT)

            huge_integer = b'{"value":' + b"9" * 4301 + b"}"
            with (
                mock.patch.object(Path, "read_bytes", return_value=huge_integer),
                self.assertRaisesRegex(CatalogError, "unsafe JSON integer"),
            ):
                load_installed_manifest(ROOT)
            with self.assertRaisesRegex(
                bootstrap.BootstrapError, "unsafe JSON integer"
            ):
                bootstrap._parse_manifest(huge_integer)

    def test_15_handler_outcome_cannot_override_authoritative_result(self) -> None:
        skill = "elmos-bigdata-evidence-certification"
        parsed = RuntimeRequest.parse(request(skill))
        record = validate_registry()[skill]
        binding = SKILL_REGISTRY[skill]
        valid = binding.handler(parsed, record)
        runtime._validate_handler_outcome(binding, parsed, record, valid)

        mutations = []
        for field, value in (
            ("state", "PASS"),
            ("production_certification", "CERTIFIED"),
        ):
            changed = copy.deepcopy(valid)
            changed[field] = value
            mutations.append(changed)
        extra = copy.deepcopy(valid)
        extra["provenance"] = {"status": "ATTESTED"}
        mutations.append(extra)
        task_raise = copy.deepcopy(valid)
        task_raise["task_ledger"][0]["runtime_evidence"] = "PASSED"
        mutations.append(task_raise)
        artifact_raise = copy.deepcopy(valid)
        artifact_raise["artifacts"][0]["production_certification"] = "CERTIFIED"
        mutations.append(artifact_raise)

        for changed in mutations:
            with (
                self.subTest(keys=sorted(changed)),
                self.assertRaisesRegex(SkillRuntimeError, "handler outcome"),
            ):
                runtime._validate_handler_outcome(binding, parsed, record, changed)

    def test_16_long_lived_process_snapshot_drift_requires_restart(self) -> None:
        initial = bootstrap.assert_repository_runtime_unchanged()
        drifted = replace(initial, runtime_tree_sha256="sha256:" + "0" * 64)
        with (
            mock.patch.object(
                bootstrap, "_verify_repository_runtime", return_value=drifted
            ),
            self.assertRaisesRegex(SkillRuntimeError, "snapshot drifted"),
        ):
            capability_manifest()


if __name__ == "__main__":
    unittest.main(verbosity=2)
