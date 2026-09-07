from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path


ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT / "src"))

from elmos_autonomous_qa.adapters import (  # noqa: E402
    ADAPTER_REGISTRY,
    AdapterContractError,
    Capability,
    Command,
    OperationMode,
    ProjectFingerprint,
    SdkOperation,
    UnsupportedAdapterError,
    adapter_for,
    capability_plan,
    detect_adapters,
    execute_adapter_contract,
    operation_support,
)
from elmos_autonomous_qa.contracts import ContractError  # noqa: E402
from elmos_autonomous_qa.gates import (  # noqa: E402
    CertificationEvidence,
    Decision,
    OutputEvidence,
    Priority,
    QualityGateInput,
    RepairDiff,
    RepairRisk,
    Requirement,
    ResultStatus,
    RunMode,
    SecurityEvidence,
    TestObservation,
    analyze_impact,
    assess_repair,
    estimate_eta,
    evaluate_quality_gate,
    evaluate_quality_gate_contract,
)


class AdapterRegistryTest(unittest.TestCase):
    def test_registry_is_exact_and_every_adapter_has_native_layouts(self) -> None:
        self.assertEqual(
            set(ADAPTER_REGISTRY),
            {
                "java-maven",
                "java-gradle",
                "kotlin-maven",
                "kotlin-gradle",
                "python",
                "dotnet",
                "go",
                "rust",
                "cmake-c-cpp",
                "php-composer",
                "javascript-node",
                "typescript-node",
                "react",
                "vue",
                "objective-c-xcode",
                "swift-package",
                "swift-xcode",
                "flutter",
            },
        )
        for key, adapter in ADAPTER_REGISTRY.items():
            with self.subTest(adapter=key):
                self.assertTrue(adapter.native_test_layouts)
                self.assertTrue(adapter.capabilities)
                self.assertEqual(set(SdkOperation), set(adapter.sdk_operations))
                for operation in SdkOperation:
                    support = operation_support(key, operation)
                    self.assertTrue(support.supported)
                    expected_mode = (
                        OperationMode.LOCAL
                        if operation
                        in {
                            SdkOperation.DETECT,
                            SdkOperation.GENERATE,
                            SdkOperation.VALIDATE,
                            SdkOperation.DIAGNOSE,
                        }
                        else OperationMode.EXTERNAL_ADAPTER_REQUIRED
                    )
                    self.assertEqual(expected_mode, support.mode)
                    self.assertTrue(support.reason)

    def test_detection_covers_every_declared_adapter(self) -> None:
        cases = {
            "java-maven": ProjectFingerprint.create(
                ("pom.xml", "src/main/java/App.java")
            ),
            "java-gradle": ProjectFingerprint.create(
                ("build.gradle", "src/main/java/App.java")
            ),
            "kotlin-maven": ProjectFingerprint.create(
                ("pom.xml", "src/main/kotlin/App.kt")
            ),
            "kotlin-gradle": ProjectFingerprint.create(
                ("build.gradle.kts", "src/main/kotlin/App.kt")
            ),
            "python": ProjectFingerprint.create(("pyproject.toml", "src/app.py")),
            "dotnet": ProjectFingerprint.create(("App.sln", "src/App/App.csproj")),
            "go": ProjectFingerprint.create(("go.mod", "main.go")),
            "rust": ProjectFingerprint.create(("Cargo.toml", "src/lib.rs")),
            "cmake-c-cpp": ProjectFingerprint.create(
                ("CMakeLists.txt", "src/main.cpp")
            ),
            "php-composer": ProjectFingerprint.create(
                ("composer.json", "src/App.php")
            ),
            "javascript-node": ProjectFingerprint.create(
                ("package.json", "src/index.js")
            ),
            "typescript-node": ProjectFingerprint.create(
                ("package.json", "tsconfig.json", "src/index.ts")
            ),
            "react": ProjectFingerprint.create(
                ("package.json", "src/App.tsx"), dependencies=("react",)
            ),
            "vue": ProjectFingerprint.create(
                ("package.json", "src/App.vue"), dependencies=("vue",)
            ),
            "objective-c-xcode": ProjectFingerprint.create(
                ("App.xcodeproj/project.pbxproj", "App/AppDelegate.m")
            ),
            "swift-package": ProjectFingerprint.create(
                ("Package.swift", "Sources/App/App.swift")
            ),
            "swift-xcode": ProjectFingerprint.create(
                ("App.xcodeproj/project.pbxproj", "App/App.swift")
            ),
            "flutter": ProjectFingerprint.create(
                ("pubspec.yaml", "lib/main.dart"), dependencies=("flutter",)
            ),
        }
        for expected, fingerprint in cases.items():
            with self.subTest(adapter=expected):
                detected = {adapter.key for adapter in detect_adapters(fingerprint)}
                self.assertIn(expected, detected)
                contract_result = execute_adapter_contract(
                    {
                        "operation": "detect",
                        "fingerprint": {
                            "paths": list(fingerprint.paths),
                            "dependencies": sorted(fingerprint.dependencies),
                            "declared_languages": sorted(
                                fingerprint.declared_languages
                            ),
                        },
                    }
                )
                self.assertEqual("SUCCEEDED", contract_result["state"])
                self.assertIn(
                    expected,
                    {
                        adapter["adapter_key"]
                        for adapter in contract_result["outputs"]["matches"]
                    },
                )
                self.assertFalse(
                    contract_result["outputs"]["command_execution_performed"]
                )
                self.assertFalse(contract_result["outputs"]["file_reads_performed"])

    def test_unknown_adapter_and_empty_fingerprint_have_no_fallback(self) -> None:
        self.assertEqual(detect_adapters(ProjectFingerprint.create(("README.md",))), ())
        no_match = execute_adapter_contract(
            {
                "operation": "detect",
                "fingerprint": {"paths": ["README.md"]},
            }
        )
        self.assertEqual("NOT_APPLICABLE", no_match["state"])
        self.assertEqual("NO_EXACT_ADAPTER_MATCH", no_match["code"])
        self.assertEqual([], no_match["outputs"]["matches"])
        self.assertFalse(no_match["outputs"]["fallback_selected"])
        with self.assertRaises(UnsupportedAdapterError):
            adapter_for("best-effort-anything")
        with self.assertRaises(AdapterContractError):
            execute_adapter_contract({"operation": "best-effort"})

    def test_unsupported_capability_is_explicit(self) -> None:
        plan = capability_plan("go", Capability.UI_E2E)
        self.assertFalse(plan.supported)
        self.assertIn("explicitly does not support", plan.unsupported_reason or "")
        with self.assertRaises(AdapterContractError):
            plan.require_commands()

    def test_commands_are_argv_only_and_reject_injection(self) -> None:
        plan = capability_plan("cmake-c-cpp", Capability.BUILD)
        self.assertEqual(len(plan.require_commands()), 2)
        for command in plan.commands:
            self.assertIs(command.shell, False)
            self.assertIsInstance(command.argv, tuple)
            self.assertIs(command.subprocess_options()["shell"], False)
        with self.assertRaises(AdapterContractError):
            Command(("sh", "-c", "echo unsafe"))
        with self.assertRaises(AdapterContractError):
            Command(("npm", "test; rm -rf workspace"))
        with self.assertRaises(AdapterContractError):
            capability_plan(
                "objective-c-xcode",
                Capability.UNIT,
                parameters={"scheme": "App; rm -rf workspace"},
            )

    def test_parameterized_native_command_requires_exact_parameters(self) -> None:
        with self.assertRaises(AdapterContractError):
            capability_plan("objective-c-xcode", Capability.UNIT)
        command = capability_plan(
            "objective-c-xcode", Capability.UNIT, parameters={"scheme": "AppTests"}
        ).require_commands()[0]
        self.assertEqual(command.argv, ("xcodebuild", "-scheme", "AppTests", "test"))

    def test_skill_contract_uses_exact_registry_without_execution_or_fallback(self) -> None:
        listed = execute_adapter_contract({"operation": "list"})
        self.assertEqual(18, listed["outputs"]["adapter_count"])
        self.assertEqual("LOCAL_EXECUTED", listed["implementation_state"])
        self.assertFalse(listed["outputs"]["command_execution_performed"])
        self.assertFalse(listed["outputs"]["file_reads_performed"])
        self.assertFalse(listed["outputs"]["file_writes_performed"])
        self.assertEqual(
            {operation.value for operation in SdkOperation},
            set(listed["outputs"]["sdk_operations"]),
        )
        for adapter in listed["outputs"]["adapters"]:
            self.assertEqual(
                {operation.value for operation in SdkOperation},
                {item["operation"] for item in adapter["sdk_operations"]},
            )
            self.assertEqual(
                {capability.value for capability in Capability},
                {
                    item["capability"]
                    for item in adapter["capability_support"]
                },
            )
            supported_capabilities = {
                item["capability"]
                for item in adapter["capability_support"]
                if item["supported"]
            }
            self.assertEqual(set(adapter["capabilities"]), supported_capabilities)
            for item in adapter["capability_support"]:
                self.assertEqual(
                    (
                        "EXTERNAL_ADAPTER_REQUIRED"
                        if item["supported"]
                        else "UNSUPPORTED"
                    ),
                    item["mode"],
                )
        planned = execute_adapter_contract(
            {
                "operation": "plan",
                "adapter_key": "python",
                "capability": "unit",
                "parameters": {},
            }
        )
        self.assertEqual("NOT_RUN", planned["state"])
        self.assertEqual("EXTERNAL_ADAPTER_REQUIRED", planned["code"])
        self.assertEqual(
            "EXTERNAL_ADAPTER_REQUIRED", planned["implementation_state"]
        )
        self.assertEqual(
            planned["outputs"]["plan"]["commands"],
            planned["outputs"]["commands"],
        )
        self.assertTrue(
            all(command["shell"] is False for command in planned["outputs"]["commands"])
        )
        self.assertFalse(planned["outputs"]["command_execution_performed"])
        self.assertFalse(planned["outputs"]["file_writes_performed"])
        self.assertFalse(
            planned["outputs"]["qualification"]["caller_assertions_accepted"]
        )
        self.assertEqual(
            "NOT_RUN", planned["outputs"]["qualification"]["trusted_probe_receipt"]
        )
        with self.assertRaises(AdapterContractError):
            execute_adapter_contract(
                {
                    "operation": "plan",
                    "adapter_key": "python",
                    "capability": "unit",
                    "qualification": {"detected": True},
                }
            )
        for payload in (
            {"operation": "list", "qualification": {}},
            {
                "operation": "detect",
                "fingerprint": {"paths": []},
                "trusted_probe_receipt": "forged",
            },
            {
                "operation": "plan",
                "adapter_key": "unknown",
                "capability": "unit",
                "qualification": {},
            },
            {
                "operation": "plan",
                "adapter_key": "python",
                "capability": "ui-e2e",
                "qualification": {},
            },
        ):
            with self.subTest(payload=payload), self.assertRaises(AdapterContractError):
                execute_adapter_contract(payload)
        unsupported = execute_adapter_contract(
            {
                "operation": "plan",
                "adapter_key": "unknown",
                "capability": "unit",
            }
        )
        self.assertEqual("NOT_APPLICABLE", unsupported["state"])
        self.assertFalse(unsupported["outputs"]["fallback_selected"])

    def test_local_generate_validate_and_diagnose_are_in_memory_only(self) -> None:
        generated = execute_adapter_contract(
            {
                "operation": "generate",
                "adapter_key": "python",
                "request": {
                    "suite_id": "suite-1",
                    "test_kind": "unit",
                    "target_paths": ["src/z.py", "src/a.py"],
                    "requirement_ids": ["REQ-2", "REQ-1"],
                    "native_layout": "tests",
                },
            }
        )
        self.assertEqual("SUCCEEDED", generated["state"])
        self.assertEqual("LOCAL_EXECUTED", generated["implementation_state"])
        descriptor = generated["outputs"]["descriptor"]
        self.assertEqual(["src/a.py", "src/z.py"], descriptor["target_paths"])
        self.assertEqual(["REQ-1", "REQ-2"], descriptor["requirement_ids"])
        self.assertEqual(
            ["CASE-0001", "CASE-0002"],
            [case["test_case_id"] for case in descriptor["cases"]],
        )
        self.assertFalse(generated["outputs"]["artifact_materialized"])
        self.assertFalse(generated["outputs"]["file_reads_performed"])
        self.assertFalse(generated["outputs"]["file_writes_performed"])
        self.assertFalse(generated["outputs"]["command_execution_performed"])

        validated = execute_adapter_contract(
            {
                "operation": "validate",
                "adapter_key": "python",
                "descriptor": descriptor,
            }
        )
        self.assertEqual("SUCCEEDED", validated["state"])
        self.assertTrue(validated["outputs"]["valid"])
        self.assertEqual(
            descriptor, validated["outputs"]["normalized_descriptor"]
        )
        self.assertFalse(validated["outputs"]["file_reads_performed"])
        self.assertFalse(validated["outputs"]["file_writes_performed"])

        diagnosed = execute_adapter_contract(
            {
                "operation": "diagnose",
                "adapter_key": "python",
                "diagnostics": [
                    {
                        "code": "W-2",
                        "severity": "warning",
                        "message": "  later   warning ",
                        "path": "src/z.py",
                        "line": 9,
                    },
                    {
                        "code": "E-1",
                        "severity": "error",
                        "message": "broken\nvalue",
                        "path": "src/a.py",
                        "line": 2,
                    },
                    {
                        "code": "E-1",
                        "severity": "ERROR",
                        "message": "broken value",
                        "path": "src/a.py",
                        "line": 2,
                    },
                ],
            }
        )
        self.assertEqual("SUCCEEDED", diagnosed["state"])
        self.assertEqual(
            ["E-1", "W-2"],
            [item["code"] for item in diagnosed["outputs"]["diagnostics"]],
        )
        self.assertEqual(
            {"ERROR": 1, "WARNING": 1, "INFO": 0},
            diagnosed["outputs"]["counts"],
        )
        self.assertFalse(diagnosed["outputs"]["command_execution_performed"])
        self.assertFalse(diagnosed["outputs"]["file_writes_performed"])

    def test_local_typed_operations_cover_every_registered_adapter(self) -> None:
        for adapter_key in ADAPTER_REGISTRY:
            with self.subTest(adapter=adapter_key, operation="generate"):
                generated = execute_adapter_contract(
                    {
                        "operation": "generate",
                        "adapter_key": adapter_key,
                        "request": {
                            "suite_id": "suite-1",
                            "test_kind": "unit",
                            "target_paths": ["src/example.txt"],
                            "requirement_ids": ["REQ-1"],
                        },
                    }
                )
                self.assertEqual("SUCCEEDED", generated["state"])
                self.assertFalse(generated["outputs"]["artifact_materialized"])

            with self.subTest(adapter=adapter_key, operation="validate"):
                validated = execute_adapter_contract(
                    {
                        "operation": "validate",
                        "adapter_key": adapter_key,
                        "descriptor": generated["outputs"]["descriptor"],
                    }
                )
                self.assertEqual("SUCCEEDED", validated["state"])
                self.assertTrue(validated["outputs"]["valid"])

            with self.subTest(adapter=adapter_key, operation="diagnose"):
                diagnosed = execute_adapter_contract(
                    {
                        "operation": "diagnose",
                        "adapter_key": adapter_key,
                        "diagnostics": [],
                    }
                )
                self.assertEqual("SUCCEEDED", diagnosed["state"])
                self.assertEqual([], diagnosed["outputs"]["diagnostics"])
                self.assertFalse(diagnosed["outputs"]["file_reads_performed"])
                self.assertFalse(diagnosed["outputs"]["file_writes_performed"])

    def test_external_operations_only_return_not_run_plans_for_every_adapter(self) -> None:
        for adapter_key in ADAPTER_REGISTRY:
            parameters = (
                {"scheme": "AppTests"}
                if adapter_key in {"objective-c-xcode", "swift-xcode"}
                else {}
            )
            with self.subTest(adapter=adapter_key, operation="execute"):
                executed = execute_adapter_contract(
                    {
                        "operation": "execute",
                        "adapter_key": adapter_key,
                        "capability": "unit",
                        "parameters": parameters,
                    }
                )
                self._assert_external_plan_is_inert(executed)
                self.assertTrue(executed["outputs"]["plan"]["commands"])
                self.assertEqual(
                    "NOT_RUN", executed["outputs"]["plan"]["execution_status"]
                )
                self.assertTrue(
                    all(
                        command["shell"] is False
                        for command in executed["outputs"]["plan"]["commands"]
                    )
                )

            with self.subTest(adapter=adapter_key, operation="collect_coverage"):
                coverage = execute_adapter_contract(
                    {
                        "operation": "collect_coverage",
                        "adapter_key": adapter_key,
                        "request": {
                            "capability": "unit",
                            "format": "native",
                            "include_paths": ["src"],
                        },
                    }
                )
                self._assert_external_plan_is_inert(coverage)
                self.assertEqual([], coverage["outputs"]["plan"]["commands"])
                self.assertEqual(
                    "NOT_RUN", coverage["outputs"]["plan"]["collection_status"]
                )

            with self.subTest(adapter=adapter_key, operation="apply_patch"):
                patch = execute_adapter_contract(
                    {
                        "operation": "apply_patch",
                        "adapter_key": adapter_key,
                        "patch": {
                            "patch_id": "repair-1",
                            "paths": ["src/app.txt"],
                            "base_digest": "sha256:" + "a" * 64,
                            "patch_digest": "sha256:" + "b" * 64,
                        },
                    }
                )
                self._assert_external_plan_is_inert(patch)
                self.assertFalse(patch["outputs"]["plan"]["patch_applied"])
                self.assertEqual([], patch["outputs"]["plan"]["commands"])
                self.assertEqual(
                    "NOT_RUN", patch["outputs"]["plan"]["mutation_status"]
                )

    def test_sdk_rejects_unsupported_and_unsafe_operation_inputs(self) -> None:
        unsupported_execution = execute_adapter_contract(
            {
                "operation": "execute",
                "adapter_key": "go",
                "capability": "ui-e2e",
                "parameters": {},
            }
        )
        self.assertEqual("NOT_APPLICABLE", unsupported_execution["state"])
        self.assertFalse(unsupported_execution["outputs"]["supported"])
        self.assertFalse(unsupported_execution["outputs"]["fallback_selected"])

        unsupported_generation = execute_adapter_contract(
            {
                "operation": "generate",
                "adapter_key": "go",
                "request": {
                    "suite_id": "suite-1",
                    "test_kind": "ui-e2e",
                    "target_paths": ["web/app.go"],
                    "requirement_ids": ["REQ-1"],
                },
            }
        )
        self.assertEqual("NOT_APPLICABLE", unsupported_generation["state"])
        self.assertFalse(unsupported_generation["outputs"]["supported"])

        unsupported_descriptor = {
            "schema_version": "elmos.autonomous-qa.adapter-test-descriptor.v1",
            "adapter_key": "go",
            "suite_id": "suite-1",
            "test_kind": "ui-e2e",
            "target_paths": ["web/app.go"],
            "requirement_ids": ["REQ-1"],
            "native_layout": "*_test.go",
            "cases": [
                {
                    "test_case_id": "CASE-0001",
                    "adapter_key": "go",
                    "test_kind": "ui-e2e",
                    "target_path": "web/app.go",
                    "requirement_ids": ["REQ-1"],
                }
            ],
        }
        unsupported_validation = execute_adapter_contract(
            {
                "operation": "validate",
                "adapter_key": "go",
                "descriptor": unsupported_descriptor,
            }
        )
        self.assertEqual("NOT_APPLICABLE", unsupported_validation["state"])
        self.assertFalse(unsupported_validation["outputs"]["supported"])

        bad_requests = (
            {
                "operation": "execute",
                "adapter_key": "objective-c-xcode",
                "capability": "unit",
                "parameters": {"scheme": "App; touch outside"},
            },
            {
                "operation": "generate",
                "adapter_key": "python",
                "request": {
                    "suite_id": "suite-1",
                    "test_kind": "unit",
                    "target_paths": ["../outside.py"],
                    "requirement_ids": ["REQ-1"],
                },
            },
            {
                "operation": "generate",
                "adapter_key": "python",
                "request": {
                    "suite_id": "suite-1",
                    "test_kind": "unit",
                    "target_paths": ["src/app.py"],
                    "requirement_ids": ["REQ-1"],
                    "source_body": "do not embed caller code",
                },
            },
            {
                "operation": "collect_coverage",
                "adapter_key": "python",
                "request": {"capability": "unit", "format": ["lcov"]},
            },
            {
                "operation": "collect_coverage",
                "adapter_key": "python",
                "request": {
                    "capability": "unit",
                    "format": "lcov",
                    "include_paths": ["../outside"],
                },
            },
            {
                "operation": "diagnose",
                "adapter_key": "python",
                "diagnostics": [
                    {
                        "code": "E-1",
                        "severity": "fatal",
                        "message": "invalid severity",
                    }
                ],
            },
            {
                "operation": "apply_patch",
                "adapter_key": "python",
                "patch": {
                    "patch_id": "repair-1",
                    "paths": ["../outside.py"],
                    "base_digest": "sha256:" + "a" * 64,
                    "patch_digest": "sha256:" + "b" * 64,
                },
            },
            {
                "operation": "apply_patch",
                "adapter_key": "python",
                "patch": {
                    "patch_id": "repair-1",
                    "paths": ["src/app.py"],
                    "base_digest": "caller-controlled",
                    "patch_digest": "sha256:" + "b" * 64,
                },
            },
            {
                "operation": "apply_patch",
                "adapter_key": "python",
                "patch": {
                    "patch_id": "repair-1",
                    "paths": ["src/app.py"],
                    "base_digest": "sha256:" + "a" * 64,
                    "patch_digest": "sha256:" + "b" * 64,
                    "diff": "untrusted patch body",
                },
            },
        )
        for payload in bad_requests:
            with self.subTest(payload=payload), self.assertRaises(AdapterContractError):
                execute_adapter_contract(payload)

        generated = execute_adapter_contract(
            {
                "operation": "generate",
                "adapter_key": "python",
                "request": {
                    "suite_id": "suite-1",
                    "test_kind": "unit",
                    "target_paths": ["src/app.py"],
                    "requirement_ids": ["REQ-1"],
                },
            }
        )["outputs"]["descriptor"]
        tampered_cases = [dict(case) for case in generated["cases"]]
        tampered_cases[0]["target_path"] = "src/other.py"
        with self.assertRaises(AdapterContractError):
            execute_adapter_contract(
                {
                    "operation": "validate",
                    "adapter_key": "python",
                    "descriptor": {**generated, "cases": tampered_cases},
                }
            )

    def _assert_external_plan_is_inert(self, result) -> None:
        self.assertEqual("NOT_RUN", result["state"])
        self.assertEqual("EXTERNAL_ADAPTER_REQUIRED", result["code"])
        self.assertEqual("EXTERNAL_ADAPTER_REQUIRED", result["implementation_state"])
        outputs = result["outputs"]
        self.assertTrue(outputs["supported"])
        self.assertTrue(outputs["plan_only"])
        self.assertEqual("NOT_RUN", outputs["external_evidence_status"])
        self.assertEqual("NOT_RUN", outputs["qualification"]["status"])
        self.assertFalse(outputs["fallback_selected"])
        self.assertFalse(outputs["shell_invocation_performed"])
        self.assertFalse(outputs["command_execution_performed"])
        self.assertFalse(outputs["file_reads_performed"])
        self.assertFalse(outputs["file_writes_performed"])
        self.assertFalse(outputs["local_operation_performed"])


def _complete_output() -> OutputEvidence:
    return OutputEvidence(
        project_output_manifest_ref="manifest:project",
        test_artifact_manifest_ref="manifest:tests",
        bundles=frozenset({"project-with-tests", "tests-only", "qa-evidence"}),
        materialized_artifact_refs=frozenset(
            {"artifact:test-p0", "artifact:test-p1", "artifact:test-p2"}
        ),
        all_artifacts_have_sha256=True,
        bundle_checksums_match=True,
        tamper_detected=False,
        test_targets_build=True,
        generated_tests_discoverable=True,
        replay_entrypoint_present=True,
        untracked_generated_files=False,
        secrets_detected=False,
        unsafe_symlink_detected=False,
        partial_output_available=True,
    )


def _complete_security() -> SecurityEvidence:
    return SecurityEvidence(
        unresolved_critical_findings=0,
        unresolved_high_findings=0,
        production_credentials_used=False,
        permissions_broadened=False,
        security_controls_disabled=False,
        direct_main_write=False,
        direct_production_write=False,
    )


def _complete_certification() -> CertificationEvidence:
    return CertificationEvidence(
        project_manifest_signed=True,
        evidence_manifest_signed=True,
        signatures_valid=True,
        signer_trusted=True,
        evidence_digests_valid=True,
        authorization_valid=True,
        independent_corpus=True,
        independent_evidence=True,
        external_validation_completed=True,
        executor_id="executor-a",
        verifier_id="verifier-b",
        signer_id="signer-c",
    )


def _passing_request() -> QualityGateInput:
    requirements = (
        Requirement("REQ-P0", Priority.P0),
        Requirement("REQ-P1", Priority.P1),
        Requirement("REQ-P2", Priority.P2),
    )
    tests = tuple(
        TestObservation(
            test_id=f"test-{priority.value.lower()}",
            status=ResultStatus.PASSED,
            requirement_refs=(requirement.requirement_id,),
            materialized_ref=f"artifact:test-{priority.value.lower()}",
            build_status=ResultStatus.PASSED,
            discovery_status=ResultStatus.PASSED,
        )
        for requirement, priority in zip(requirements, (Priority.P0, Priority.P1, Priority.P2))
    )
    return QualityGateInput(
        mode=RunMode.VERIFY,
        requirements=requirements,
        tests=tests,
        output=_complete_output(),
        security=_complete_security(),
        certification=_complete_certification(),
        run_succeeded=True,
    )


class QualityGateTest(unittest.TestCase):
    def test_complete_evidence_reaches_only_external_gate_boundary(self) -> None:
        report = evaluate_quality_gate(_passing_request())
        self.assertEqual(report.decision, Decision.READY_FOR_EXTERNAL_GATE)
        self.assertTrue(report.ready_for_external_gate)
        self.assertFalse(report.certified)
        self.assertIn("never certifies", report.certification_boundary)
        self.assertEqual(report.executable_coverage[Priority.P0], 1.0)
        self.assertEqual(report.executable_coverage[Priority.P1], 1.0)
        self.assertEqual(report.executable_coverage[Priority.P2], 1.0)

    def test_every_nonpassing_terminal_status_fails_closed(self) -> None:
        for status in (
            ResultStatus.FAILED,
            ResultStatus.BLOCKED,
            ResultStatus.FLAKY,
            ResultStatus.FLAKY_CONFIRMED,
            ResultStatus.NOT_RUN,
            ResultStatus.UNKNOWN,
            ResultStatus.SKIPPED,
        ):
            with self.subTest(status=status):
                request = _passing_request()
                tests = (replace(request.tests[0], status=status),) + request.tests[1:]
                report = evaluate_quality_gate(replace(request, tests=tests))
                self.assertNotEqual(report.decision, Decision.READY_FOR_EXTERNAL_GATE)
                self.assertFalse(report.certified)

    def test_missing_materialization_build_or_discovery_never_passes(self) -> None:
        request = _passing_request()
        mutations = (
            replace(request.tests[0], materialized_ref=None),
            replace(request.tests[0], build_status=ResultStatus.NOT_RUN),
            replace(request.tests[0], discovery_status=ResultStatus.UNKNOWN),
        )
        for observation in mutations:
            with self.subTest(observation=observation):
                tests = (observation,) + request.tests[1:]
                self.assertFalse(
                    evaluate_quality_gate(replace(request, tests=tests)).ready_for_external_gate
                )

    def test_repair_mode_requires_the_patch_bundle(self) -> None:
        request = replace(_passing_request(), mode=RunMode.REPAIR)
        report = evaluate_quality_gate(request)
        self.assertFalse(report.ready_for_external_gate)
        self.assertTrue(
            any(finding.code == "output.required-bundles" for finding in report.findings)
        )

    def test_p2_executable_coverage_threshold_is_strict(self) -> None:
        requirements = tuple(Requirement(f"P2-{index}", Priority.P2) for index in range(50))
        tests = tuple(
            TestObservation(
                test_id=f"p2-test-{index}",
                status=ResultStatus.PASSED,
                requirement_refs=(f"P2-{index}",),
                materialized_ref=f"p2-artifact-{index}",
                build_status=ResultStatus.PASSED,
                discovery_status=ResultStatus.PASSED,
            )
            for index in range(49)
        )
        output = replace(
            _complete_output(),
            materialized_artifact_refs=frozenset(
                {f"p2-artifact-{index}" for index in range(49)}
            ),
        )
        request = replace(
            _passing_request(), requirements=requirements, tests=tests, output=output
        )
        at_threshold = evaluate_quality_gate(request)
        self.assertEqual(at_threshold.executable_coverage[Priority.P2], 0.98)
        self.assertTrue(at_threshold.ready_for_external_gate)

        below = replace(request, tests=tests[:-1])
        below_report = evaluate_quality_gate(
            replace(
                below,
                output=replace(
                    output,
                    materialized_artifact_refs=frozenset(
                        {f"p2-artifact-{index}" for index in range(48)}
                    ),
                ),
            )
        )
        self.assertLess(below_report.executable_coverage[Priority.P2], 0.98)
        self.assertEqual(below_report.decision, Decision.FAILED)

    def test_signature_trust_tamper_and_identity_boundaries(self) -> None:
        request = _passing_request()
        variants = (
            replace(request.certification, project_manifest_signed=False),
            replace(request.certification, signatures_valid=None),
            replace(request.certification, signer_trusted=False),
            replace(request.certification, evidence_digests_valid=False),
            replace(request.certification, verifier_id="executor-a"),
        )
        for certification in variants:
            with self.subTest(certification=certification):
                report = evaluate_quality_gate(
                    replace(request, certification=certification)
                )
                self.assertFalse(report.ready_for_external_gate)
                self.assertFalse(report.certified)
        tampered = replace(request, output=replace(request.output, tamper_detected=True))
        self.assertEqual(evaluate_quality_gate(tampered).decision, Decision.FAILED)

    def test_orphans_unknown_refs_and_security_unknowns_fail_closed(self) -> None:
        request = _passing_request()
        orphan = replace(request.tests[0], requirement_refs=(), risk_refs=())
        report = evaluate_quality_gate(replace(request, tests=(orphan,) + request.tests[1:]))
        self.assertFalse(report.ready_for_external_gate)
        unknown_security = replace(
            request, security=replace(request.security, unresolved_high_findings=None)
        )
        self.assertEqual(evaluate_quality_gate(unknown_security).decision, Decision.BLOCKED)

    def test_json_contract_preserves_external_boundary(self) -> None:
        request = _passing_request()
        payload = {
            "mode": request.mode.value,
            "requirements": [
                {
                    "requirement_id": item.requirement_id,
                    "priority": item.priority.value,
                    "required": item.required,
                }
                for item in request.requirements
            ],
            "tests": [
                {
                    "test_id": item.test_id,
                    "status": item.status.value,
                    "requirement_refs": list(item.requirement_refs),
                    "risk_refs": list(item.risk_refs),
                    "materialized_ref": item.materialized_ref,
                    "build_status": item.build_status.value,
                    "discovery_status": item.discovery_status.value,
                    "required": item.required,
                }
                for item in request.tests
            ],
            "output": {
                "project_output_manifest_ref": request.output.project_output_manifest_ref,
                "test_artifact_manifest_ref": request.output.test_artifact_manifest_ref,
                "bundles": sorted(request.output.bundles),
                "materialized_artifact_refs": sorted(request.output.materialized_artifact_refs),
                "all_artifacts_have_sha256": True,
                "bundle_checksums_match": True,
                "tamper_detected": False,
                "test_targets_build": True,
                "generated_tests_discoverable": True,
                "replay_entrypoint_present": True,
                "untracked_generated_files": False,
                "secrets_detected": False,
                "unsafe_symlink_detected": False,
                "partial_output_available": True,
            },
            "security": {
                "unresolved_critical_findings": 0,
                "unresolved_high_findings": 0,
                "production_credentials_used": False,
                "permissions_broadened": False,
                "security_controls_disabled": False,
                "direct_main_write": False,
                "direct_production_write": False,
            },
            "certification": {
                "project_manifest_signed": True,
                "evidence_manifest_signed": True,
                "signatures_valid": True,
                "signer_trusted": True,
                "evidence_digests_valid": True,
                "authorization_valid": True,
                "independent_corpus": True,
                "independent_evidence": True,
                "external_validation_completed": True,
                "executor_id": "executor-a",
                "verifier_id": "verifier-b",
                "signer_id": "signer-c",
            },
            "run_succeeded": True,
        }
        result = evaluate_quality_gate_contract(payload)
        self.assertEqual("BLOCKED", result["state"])
        self.assertFalse(result["outputs"]["caller_certification_assertions_accepted"])
        self.assertEqual("NOT_RUN", result["outputs"]["trusted_external_receipt"])
        self.assertFalse(result["outputs"]["certified"])

    def test_json_contract_rejects_non_boolean_required_flags(self) -> None:
        with self.assertRaises(ValueError):
            evaluate_quality_gate_contract(
                {
                    "requirements": [
                        {"requirement_id": "REQ-P0", "priority": "P0", "required": "true"}
                    ],
                    "tests": [{"test_id": "test-1", "status": "PASSED"}],
                    "output": {},
                    "security": {},
                }
            )

    def test_json_contract_rejects_unknown_fields_at_every_boundary(self) -> None:
        base = {
            "requirements": [
                {"requirement_id": "REQ-P0", "priority": "P0", "required": True}
            ],
            "tests": [
                {
                    "test_id": "test-1",
                    "status": "NOT_RUN",
                    "requirement_refs": ["REQ-P0"],
                }
            ],
            "output": {},
            "security": {},
        }
        variants = {
            "request": {**base, "unexpected": True},
            "requirement": {
                **base,
                "requirements": [
                    {
                        "requirement_id": "REQ-P0",
                        "priority": "P0",
                        "required": True,
                        "unexpected": True,
                    }
                ],
            },
            "test": {
                **base,
                "tests": [
                    {
                        "test_id": "test-1",
                        "status": "NOT_RUN",
                        "unexpected": True,
                    }
                ],
            },
            "output": {**base, "output": {"unexpected": True}},
            "security": {**base, "security": {"unexpected": True}},
            "certification": {
                **base,
                "certification": {"unexpected": True},
            },
            "runtime-context": {
                **base,
                "_runtime_context": {
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                    "actor_id": None,
                    "request_id": "request-1",
                    "idempotency_key": None,
                    "unexpected": True,
                },
            },
        }
        for boundary, payload in variants.items():
            with self.subTest(boundary=boundary):
                with self.assertRaisesRegex(ContractError, "unsupported fields"):
                    evaluate_quality_gate_contract(payload)


class RepairEtaImpactTest(unittest.TestCase):
    def test_repair_forbidden_diffs_and_self_approval_are_rejected(self) -> None:
        forbidden = RepairDiff(
            "src/service.py",
            RepairRisk.HIGH,
            product_code_changed=True,
            weakened_assertion=True,
        )
        assessment = assess_repair(
            (forbidden,),
            approval_ref="approval-1",
            approver_id="executor-a",
            executor_id="executor-a",
            full_regression_status=ResultStatus.PASSED,
            tests_rematerialized=True,
            lineage_updated=True,
            trusted_receipt_valid=True,
        )
        self.assertFalse(assessment.allowed)
        self.assertEqual(assessment.maximum_risk, RepairRisk.HIGH)

    def test_low_risk_repair_with_full_regression_can_be_prepared(self) -> None:
        assessment = assess_repair(
            (RepairDiff("src/service.py", RepairRisk.LOW, product_code_changed=True),),
            approval_ref=None,
            approver_id=None,
            executor_id="executor-a",
            full_regression_status=ResultStatus.PASSED,
            tests_rematerialized=True,
            lineage_updated=True,
            trusted_receipt_valid=True,
        )
        self.assertTrue(assessment.allowed)

    def test_eta_is_machine_runtime_only_and_unknown_without_progress(self) -> None:
        unknown = estimate_eta(completed_units=0, total_units=10, elapsed_seconds=5)
        self.assertEqual(unknown.state, "UNKNOWN")
        self.assertIsNone(unknown.remaining_seconds)
        estimated = estimate_eta(
            completed_units=5,
            total_units=10,
            elapsed_seconds=20,
            recent_unit_durations=(4, 4, 4),
        )
        self.assertEqual(estimated.state, "ESTIMATED")
        self.assertEqual(estimated.remaining_seconds, 20.0)

    def test_unknown_impact_requires_full_regression(self) -> None:
        exact = analyze_impact(
            ("src/a.py",),
            exact_path_to_tests={"src/a.py": ("test-a",)},
            all_tests=("test-a", "test-b"),
        )
        self.assertEqual(exact.impacted_tests, ("test-a",))
        self.assertFalse(exact.full_regression_required)
        unknown = analyze_impact(
            ("src/unknown.py",),
            exact_path_to_tests={"src/a.py": ("test-a",)},
            all_tests=("test-a", "test-b"),
        )
        self.assertEqual(unknown.impacted_tests, ("test-a", "test-b"))
        self.assertTrue(unknown.full_regression_required)


if __name__ == "__main__":
    unittest.main()
