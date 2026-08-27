from __future__ import annotations

import copy
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLING_ROOT = REPOSITORY_ROOT / "tooling"
if str(TOOLING_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLING_ROOT))

import integrate_frontend_to_miniapp_skills as integration  # noqa: E402


class FrontendToMiniAppIntegrationTest(unittest.TestCase):
    def temporary_repository(
        self,
    ) -> tuple[tempfile.TemporaryDirectory[str], Path, Path, Path]:
        temporary = tempfile.TemporaryDirectory(prefix="frontend-miniapp-integration-")
        root = Path(temporary.name)
        archive = root / integration.ARCHIVE_RELATIVE
        archive.parent.mkdir(parents=True)
        shutil.copy2(REPOSITORY_ROOT / integration.ARCHIVE_RELATIVE, archive)
        source = root / integration.PACKAGE_RELATIVE
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            REPOSITORY_ROOT / integration.PACKAGE_RELATIVE,
            source,
            copy_function=shutil.copy2,
        )
        for relative in integration.RUNTIME_IMPLEMENTATION_FILES:
            source_runtime_file = REPOSITORY_ROOT / relative
            destination_runtime_file = root / relative
            destination_runtime_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_runtime_file, destination_runtime_file)
        shutil.copy2(REPOSITORY_ROOT / "Makefile", root / "Makefile")
        for engine_path in (
            integration.FRONTEND_ENGINE_PATH,
            integration.COMPONENT_ADAPTER_PATH,
        ):
            source_node_modules = REPOSITORY_ROOT / engine_path / "node_modules"
            destination_node_modules = root / engine_path / "node_modules"
            if not source_node_modules.is_dir() or source_node_modules.is_symlink():
                self.fail(f"qualification node_modules fixture is unavailable: {engine_path}")
            destination_node_modules.symlink_to(
                source_node_modules,
                target_is_directory=True,
            )
        return temporary, root, source, archive

    def write_valid_local_receipt(self, root: Path) -> dict[str, object]:
        runtime = integration._runtime_implementation(root)
        environment = integration._local_qualification_environment(
            repository_root=root,
        )
        observed_at = integration._utc_timestamp()
        receipt_root = root / integration.LOCAL_RECEIPT_ROOT_RELATIVE
        logs = receipt_root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        expected_counts = {
            command.command_id: command.expected_test_count
            for command in integration.LOCAL_QUALIFICATION_COMMANDS
            if command.expected_test_count is not None
        }
        outputs = {
            "component-build": b"component build passed\n",
            "component-tests": (
                "Tests:       "
                f"{expected_counts['component-tests']} passed, "
                f"{expected_counts['component-tests']} total\n"
            ).encode(),
            "frontend-build": b"frontend build passed\n",
            "frontend-tests": (
                f"ℹ tests {expected_counts['frontend-tests']}\n"
                f"ℹ pass {expected_counts['frontend-tests']}\n"
                "ℹ fail 0\nℹ skipped 0\n"
            ).encode(),
            "integration-tests": (
                f"Ran {expected_counts['integration-tests']} tests in 1.000s\n\nOK\n"
            ).encode(),
        }
        records: list[dict[str, object]] = []
        for command in integration.LOCAL_QUALIFICATION_COMMANDS:
            output = outputs[command.command_id]
            log = logs / f"{command.command_id}.log"
            log.write_bytes(output)
            record: dict[str, object] = {
                "id": command.command_id,
                **integration._qualification_command_binding(command),
                "resolved_cwd": str((root / command.relative_cwd).resolve()),
                "resolved_argv": list(
                    integration._qualification_execution_argv(
                        command,
                        environment,
                        root,
                    )
                ),
                "started_at": observed_at,
                "ended_at": observed_at,
                "duration_ms": 0,
                "state": "PASSED",
                "exit_code": 0,
                "evidence": {
                    "path": (
                        integration.LOCAL_RECEIPT_ROOT_RELATIVE
                        / "logs"
                        / f"{command.command_id}.log"
                    ).as_posix(),
                    "bytes": len(output),
                    "sha256": integration.digest(output),
                },
            }
            if command.result_parser:
                record["expected_test_count"] = command.expected_test_count
                record.update(
                    integration._parse_test_counts(
                        command.result_parser,
                        output.decode("utf-8"),
                        command.command_id,
                    )
                )
            records.append(record)
        receipt: dict[str, object] = {
            "schema_version": "elmos.frontend-to-miniapp.local-runtime-receipt.v1",
            "implementation_digest": runtime["implementation_digest"],
            "qualification_suite_digest": integration._qualification_suite_digest(),
            "environment": environment,
            "started_at": observed_at,
            "ended_at": observed_at,
            "duration_ms": 0,
            "commands": records,
        }
        receipt["receipt_digest"] = integration._receipt_digest(receipt)
        (receipt_root / "receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return receipt

    def rewrite_receipt(
        self,
        root: Path,
        receipt: dict[str, object],
        *,
        recompute_digest: bool,
    ) -> None:
        if recompute_digest:
            receipt["receipt_digest"] = integration._receipt_digest(receipt)
        (root / integration.LOCAL_RECEIPT_RELATIVE).write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def write_archive(
        self,
        path: Path,
        entries: list[tuple[str, bytes, int]],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as handle:
            for name, content, mode in entries:
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = mode << 16
                handle.writestr(info, content)

    def inspect_untrusted(self, path: Path) -> dict[str, integration.ArchiveRecord]:
        return integration.inspect_archive(
            path,
            trusted_sha256=None,
            expected_entry_count=None,
            expected_total_bytes=None,
            expected_mode_counts=None,
        )

    def test_source_contract_has_exact_inventory_dag_and_compiled_contracts(self) -> None:
        source = REPOSITORY_ROOT / integration.PACKAGE_RELATIVE
        archive = REPOSITORY_ROOT / integration.ARCHIVE_RELATIVE
        summary = integration.validate_source(source, archive)
        temporary, root, temporary_source, temporary_archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        expected = integration.build_expected(
            temporary_source,
            temporary_archive,
            root,
        )

        self.assertEqual(len(summary["archive_records"]), 217)
        self.assertEqual(len(summary["checksums"]), 216)
        self.assertEqual(len(summary["skills"]), 22)
        self.assertEqual(summary["dependency_edge_count"], 53)
        self.assertEqual(len(summary["topological_order"]), 22)
        self.assertEqual(
            [record["source_name"] for record in expected["manifest"]["skills"]],
            list(integration.EXPECTED_SKILLS),
        )
        self.assertEqual(len(expected["compiled_contracts"]["contracts"]), 22)
        runtime = expected["compiled_contracts"]["runtime_implementation"]
        self.assertEqual(runtime["state"], "HANDLER_IMPLEMENTED")
        self.assertEqual(
            len(runtime["files"]),
            len(integration.RUNTIME_IMPLEMENTATION_FILES) + 1,
        )
        self.assertEqual(
            runtime["files"][-1]["path"],
            "Makefile#frontend-to-miniapp-skills",
        )
        self.assertRegex(runtime["implementation_digest"], r"^sha256:[a-f0-9]{64}$")
        self.assertEqual(
            expected["compiled_contracts"]["runtime_evidence_status"], "DECLARED"
        )
        self.assertEqual(expected["compiled_contracts"]["certification"], "NOT_CERTIFIED")
        expected_package_binding = {
            "source_schema": (
                "skills/elmos-frontend-to-miniapp-skills-v1.0.0/"
                "schemas/conversion-request.schema.json"
            ),
            "request_case": "snake_case",
            "wrapper_fields": [
                "packageRequest",
                "files",
                "versionBindings",
                "evidenceBindings",
            ],
            "handler_action": "run-package",
            "handler_input_field": "packageInput",
            "validator": "validateMiniappPackageConversionInput",
            "compiler": "compileMiniappPackageConversionInput",
            "runner": "runMiniappPackageConversion",
            "cli_command": "npm run miniapp -- package",
            "input_boundary": "caller-supplied-in-memory-files-no-disk-discovery",
        }
        self.assertEqual(
            expected["compiled_contracts"]["runtime_binding"][
                "canonical_package_request"
            ],
            expected_package_binding,
        )
        for contract in expected["compiled_contracts"]["contracts"]:
            self.assertTrue(contract["required_outputs"])
            self.assertTrue(contract["gates"])
            self.assertFalse(contract["side_effects_authorized"])
            self.assertEqual(contract["contract_state"], "HANDLER_IMPLEMENTED")
            self.assertEqual(contract["runtime_evidence_status"], "DECLARED")
            self.assertEqual(contract["certification"], "NOT_CERTIFIED")
            authority = contract["runtime_binding"]["runtime_authority"]
            self.assertEqual(
                contract["runtime_binding"]["canonical_package_request"],
                expected_package_binding,
            )
            adapter = contract["runtime_binding"]["component_adapter"]
            self.assertEqual(authority["package_path"], "engines/frontend-client-engine")
            self.assertEqual(authority["cli_command"], "npm run miniapp")
            self.assertEqual(authority["cli_entrypoint"], "dist/src/miniapp-cli.js")
            self.assertEqual(authority["structured_request_handler"], "handleMiniappSkillRequest")
            self.assertEqual(authority["json_handler"], "runMiniappSkillJson")
            self.assertEqual(authority["full_conversion_handler"], "runMiniappConversion")
            self.assertEqual(
                authority["package_conversion_handler"],
                "runMiniappPackageConversion",
            )
            self.assertEqual(
                authority["package_cli_command"],
                "npm run miniapp -- package",
            )
            self.assertEqual(authority["single_skill_handler"], "executeMiniappSkill")
            self.assertEqual(authority["skill_key"], contract["source_name"])
            self.assertEqual(adapter["package_path"], "engines/component-dialect-engine")
            self.assertEqual(adapter["cli_command"], "npm run miniapp-worker")
            self.assertEqual(adapter["structured_request_handler"], "handleMiniAppWorkerRequest")
            self.assertEqual(adapter["json_handler"], "runMiniAppWorkerJson")
            self.assertEqual(adapter["emitter"], "emitPlatformMiniApp")

    def test_safe_extract_preserves_regular_file_modes(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="frontend-miniapp-extract-")
        self.addCleanup(temporary.cleanup)
        destination = Path(temporary.name) / integration.PACKAGE_RELATIVE
        result = integration.extract_archive(
            REPOSITORY_ROOT / integration.ARCHIVE_RELATIVE,
            destination,
        )

        self.assertEqual(result["dependency_edge_count"], 53)
        self.assertEqual(
            stat.S_IMODE((destination / "verify.sh").stat().st_mode), 0o755
        )
        self.assertEqual(
            stat.S_IMODE(
                (
                    destination
                    / ".agents/skills/frontend-to-miniapp-orchestrator/SKILL.md"
                ).stat().st_mode
            ),
            0o644,
        )

    def test_archive_sha256_tamper_fails_before_extraction(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="frontend-miniapp-archive-")
        self.addCleanup(temporary.cleanup)
        archive = Path(temporary.name) / "tampered.zip"
        shutil.copy2(REPOSITORY_ROOT / integration.ARCHIVE_RELATIVE, archive)
        with archive.open("ab") as handle:
            handle.write(b"tamper")

        with self.assertRaisesRegex(integration.IntegrationError, "trusted SHA-256 mismatch"):
            integration.validate_archive(archive)

    def test_archive_path_traversal_is_rejected(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="frontend-miniapp-archive-")
        self.addCleanup(temporary.cleanup)
        archive = Path(temporary.name) / "traversal.zip"
        self.write_archive(
            archive,
            [
                (
                    f"{integration.PACKAGE_DIRECTORY}/../escape.txt",
                    b"escape",
                    stat.S_IFREG | 0o644,
                )
            ],
        )

        with self.assertRaisesRegex(integration.IntegrationError, "escapes|normalized"):
            self.inspect_untrusted(archive)

    def test_duplicate_archive_path_is_rejected(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="frontend-miniapp-archive-")
        self.addCleanup(temporary.cleanup)
        archive = Path(temporary.name) / "duplicate.zip"
        name = f"{integration.PACKAGE_DIRECTORY}/duplicate.txt"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            self.write_archive(
                archive,
                [
                    (name, b"one", stat.S_IFREG | 0o644),
                    (name, b"two", stat.S_IFREG | 0o644),
                ],
            )

        with self.assertRaisesRegex(integration.IntegrationError, "duplicate archive entry"):
            self.inspect_untrusted(archive)

    def test_archive_symlink_is_rejected(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="frontend-miniapp-archive-")
        self.addCleanup(temporary.cleanup)
        archive = Path(temporary.name) / "symlink.zip"
        self.write_archive(
            archive,
            [
                (
                    f"{integration.PACKAGE_DIRECTORY}/escape-link",
                    b"../../outside",
                    stat.S_IFLNK | 0o777,
                )
            ],
        )

        with self.assertRaisesRegex(integration.IntegrationError, "not a Unix regular file"):
            self.inspect_untrusted(archive)

    def test_archive_entry_size_limit_is_enforced(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="frontend-miniapp-archive-")
        self.addCleanup(temporary.cleanup)
        archive = Path(temporary.name) / "oversized.zip"
        self.write_archive(
            archive,
            [
                (
                    f"{integration.PACKAGE_DIRECTORY}/oversized.bin",
                    b"x" * (integration.MAX_ARCHIVE_ENTRY_BYTES + 1),
                    stat.S_IFREG | 0o644,
                )
            ],
        )

        with self.assertRaisesRegex(integration.IntegrationError, "exceeds size limit"):
            self.inspect_untrusted(archive)

    def test_extracted_source_tamper_fails_archive_binding(self) -> None:
        temporary, _root, source, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        tampered = source / ".agents/skills/miniapp-semantic-ir/SKILL.md"
        tampered.write_bytes(tampered.read_bytes() + b"\nTAMPERED\n")

        with self.assertRaisesRegex(integration.IntegrationError, "pinned archive"):
            integration.validate_source(source, archive)

    def test_dependency_cycle_is_rejected(self) -> None:
        source = REPOSITORY_ROOT / integration.PACKAGE_RELATIVE
        manifest = copy.deepcopy(
            json.loads((source / "skill-manifest.json").read_text(encoding="utf-8"))
        )
        manifest["skills"][1]["depends_on"] = ["vue-to-miniapp-analyzer"]

        with self.assertRaisesRegex(integration.IntegrationError, "cycle"):
            integration.assert_dependency_dag(manifest["skills"])

    def test_runtime_catalog_exactly_matches_canonical_manifest_dag_and_tasks(self) -> None:
        source = REPOSITORY_ROOT / integration.PACKAGE_RELATIVE
        manifest = json.loads(
            (source / "skill-manifest.json").read_text(encoding="utf-8")
        )
        runtime_path = (
            REPOSITORY_ROOT
            / "engines/frontend-client-engine/src/miniapp-skill-runtime.ts"
        )
        parser = r"""
import fs from "node:fs";
import ts from "typescript";

const path = process.argv[1];
const sourceText = fs.readFileSync(path, "utf8");
const sourceFile = ts.createSourceFile(
  path,
  sourceText,
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.TS,
);

function unwrap(node) {
  while (
    ts.isAsExpression(node)
    || ts.isTypeAssertionExpression(node)
    || ts.isParenthesizedExpression(node)
    || ts.isSatisfiesExpression(node)
  ) node = node.expression;
  return node;
}

function propertyName(node) {
  if (ts.isIdentifier(node) || ts.isStringLiteral(node)) return node.text;
  throw new Error(`unsupported catalog property name: ${node.getText(sourceFile)}`);
}

function stringValue(node, label) {
  const value = unwrap(node);
  if (!ts.isStringLiteral(value) && !ts.isNoSubstitutionTemplateLiteral(value)) {
    throw new Error(`${label} must be a static string literal`);
  }
  return value.text;
}

function stringArray(node, label) {
  const value = unwrap(node);
  if (!ts.isArrayLiteralExpression(value)) {
    throw new Error(`${label} must be a static array literal`);
  }
  return value.elements.map((element, index) =>
    stringValue(element, `${label}[${index}]`));
}

let declaration;
for (const statement of sourceFile.statements) {
  if (!ts.isVariableStatement(statement)) continue;
  for (const candidate of statement.declarationList.declarations) {
    if (ts.isIdentifier(candidate.name)
      && candidate.name.text === "MINIAPP_SKILL_CATALOG") declaration = candidate;
  }
}
if (!declaration?.initializer) throw new Error("MINIAPP_SKILL_CATALOG is absent");
const initializer = unwrap(declaration.initializer);
if (!ts.isArrayLiteralExpression(initializer)) {
  throw new Error("MINIAPP_SKILL_CATALOG must be a static array literal");
}
const catalog = initializer.elements.map((rawEntry, index) => {
  const entry = unwrap(rawEntry);
  if (!ts.isObjectLiteralExpression(entry)) {
    throw new Error(`catalog[${index}] must be an object literal`);
  }
  const properties = new Map();
  for (const property of entry.properties) {
    if (!ts.isPropertyAssignment(property)) {
      throw new Error(`catalog[${index}] contains a non-static property`);
    }
    properties.set(propertyName(property.name), property.initializer);
  }
  for (const required of ["name", "dependsOn", "taskIds"]) {
    if (!properties.has(required)) throw new Error(`catalog[${index}].${required} is absent`);
  }
  return {
    name: stringValue(properties.get("name"), `catalog[${index}].name`),
    depends_on: stringArray(
      properties.get("dependsOn"),
      `catalog[${index}].dependsOn`,
    ),
    task_ids: stringArray(
      properties.get("taskIds"),
      `catalog[${index}].taskIds`,
    ),
  };
});
process.stdout.write(JSON.stringify(catalog));
"""
        completed = subprocess.run(
            [
                "node",
                "--input-type=module",
                "--eval",
                parser,
                str(runtime_path),
            ],
            cwd=REPOSITORY_ROOT / "engines/frontend-client-engine",
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        runtime_catalog = json.loads(completed.stdout)
        canonical_catalog = [
            {
                "name": entry["name"],
                "depends_on": entry["depends_on"],
                "task_ids": entry["task_ids"],
            }
            for entry in manifest["skills"]
        ]
        self.assertEqual(len(runtime_catalog), 22)
        self.assertEqual(runtime_catalog, canonical_catalog)

    def test_write_and_check_install_exact_dual_roots(self) -> None:
        temporary, root, source, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        expected = integration.write_install(root, source, archive)
        checked = integration.check_install(root, source, archive)
        self.assertEqual(expected["manifest_bytes"], checked["manifest_bytes"])
        refreshed = integration.refresh_owned_install(root, source, archive)
        self.assertEqual(expected["manifest_bytes"], refreshed["manifest_bytes"])

        manifest_path = root / integration.DOC_RELATIVE / "installed-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["source_archive_sha256"], "sha256:" + integration.EXPECTED_ARCHIVE_SHA256)
        self.assertEqual(manifest["skill_count"], 22)
        self.assertEqual(manifest["dependency_edge_count"], 53)
        self.assertTrue(manifest["dependency_dag_valid"])
        self.assertTrue(manifest["dual_root_byte_identical"])
        self.assertFalse(manifest["reverse_routes_implied"])
        self.assertEqual(manifest["contract_state"], "HANDLER_IMPLEMENTED")
        self.assertEqual(manifest["runtime_evidence_status"], "DECLARED")
        self.assertEqual(manifest["external_evidence_status"], "NOT_RUN")
        self.assertEqual(manifest["certification"], "NOT_CERTIFIED")
        evidence = json.loads(
            (root / integration.DOC_RELATIVE / "local-runtime-evidence.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(evidence["state"], "DECLARED")
        self.assertEqual(evidence["receipt"]["state"], "ABSENT")
        self.assertTrue(
            all(command["state"] == "NOT_RUN" for command in evidence["commands"])
        )
        evidence_commands = {command["id"]: command for command in evidence["commands"]}
        self.assertEqual(evidence_commands["component-tests"]["expected_test_count"], 63)
        self.assertEqual(evidence_commands["frontend-tests"]["expected_test_count"], 60)
        self.assertEqual(evidence["official_platform_builds"], "NOT_RUN")
        self.assertEqual(evidence["independent_verification"], "NOT_RUN")
        self.assertEqual(evidence["certification"], "NOT_CERTIFIED")
        self.assertEqual(
            manifest["runtime_binding"]["runtime_authority"]["package_path"],
            "engines/frontend-client-engine",
        )
        self.assertEqual(
            manifest["runtime_binding"]["runtime_authority"]["cli_command"],
            "npm run miniapp",
        )
        self.assertEqual(
            manifest["runtime_binding"]["canonical_package_request"][
                "handler_action"
            ],
            "run-package",
        )
        self.assertEqual(
            manifest["runtime_binding"]["canonical_package_request"][
                "handler_input_field"
            ],
            "packageInput",
        )
        readme = (root / integration.DOC_RELATIVE / "README.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("npm run miniapp -- package", readme)
        self.assertIn('"action":"run-package"', readme)
        self.assertIn("validateMiniappPackageConversionInput", readme)
        self.assertIn("compileMiniappPackageConversionInput", readme)
        self.assertIn("node_modules/.bin/tsc", readme)
        self.assertIn("node_modules/.bin/jest", readme)
        self.assertIn("canonical execution path, version, entrypoint byte count", readme)
        self.assertIn("do not claim a digest of the entire dependency tree", readme)
        self.assertIn("--closeout-portable", readme)
        self.assertIn("owned `0700` system temporary archive", readme)
        target = integration._frontend_make_target_payload(root).decode("utf-8")
        self.assertIn("trap closeout EXIT", target)
        self.assertIn("--closeout-portable", target)
        self.assertLess(target.index("--qualify-local"), target.index("--refresh-owned"))
        self.assertLess(target.index("--refresh-owned"), target.index("--check"))

        for record in manifest["skills"]:
            name = record["source_name"]
            runtime = root / integration.RUNTIME_RELATIVE / name
            workspace = root / integration.WORKSPACE_RELATIVE / name
            self.assertEqual(integration._read_tree(runtime), integration._read_tree(workspace))
            installed = (runtime / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("## Repository Integration Boundary", installed)
            self.assertIn("`DECLARED`", installed)
            self.assertIn("`NOT_RUN`", installed)
            self.assertIn("`NOT_CERTIFIED`", installed)
            self.assertIn("`run-package`", installed)
            self.assertIn("`packageInput`", installed)
            compiled = json.loads(
                (runtime / "compiled-contract.json").read_text(encoding="utf-8")
            )
            self.assertEqual(compiled["source_name"], name)
            self.assertEqual(compiled["contract_state"], "HANDLER_IMPLEMENTED")
            self.assertEqual(compiled["runtime_evidence_status"], "DECLARED")
            self.assertEqual(compiled["certification"], "NOT_CERTIFIED")
            self.assertEqual(
                compiled["runtime_binding"]["runtime_authority"]["skill_key"], name
            )
            self.assertEqual(
                compiled["runtime_binding"]["canonical_package_request"][
                    "handler_action"
                ],
                "run-package",
            )
            self.assertTrue((runtime / "agents/openai.yaml").is_file())

        self.write_valid_local_receipt(root)
        executed = integration.refresh_owned_install(root, source, archive)
        self.assertEqual(
            executed["manifest"]["runtime_evidence_status"], "LOCAL_EXECUTED"
        )
        executed_evidence = json.loads(
            (root / integration.DOC_RELATIVE / "local-runtime-evidence.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(executed_evidence["state"], "LOCAL_EXECUTED")
        self.assertEqual(executed_evidence["receipt"]["state"], "VERIFIED")
        self.assertEqual(
            set(executed_evidence["receipt"]["environment"]["executables"]),
            {
                "node",
                "npm",
                "pnpm",
                "uv",
                "python",
                "schema_python",
                "frontend_tsc",
                "component_tsc",
                "component_jest",
            },
        )
        self.assertEqual(
            executed_evidence["receipt"]["environment"]["variables"][
                "ELMOS_MINIAPP_SCHEMA_PYTHON"
            ],
            executed_evidence["receipt"]["environment"]["executables"][
                "schema_python"
            ]["path"],
        )
        for tool_name, relative in (
            ("frontend_tsc", integration.FRONTEND_TSC_RELATIVE),
            ("component_tsc", integration.COMPONENT_TSC_RELATIVE),
            ("component_jest", integration.COMPONENT_JEST_RELATIVE),
        ):
            binding = executed_evidence["receipt"]["environment"]["executables"][
                tool_name
            ]
            self.assertEqual(binding["path"], str(root.resolve() / relative))
            self.assertEqual(binding["repository_relative_path"], relative.as_posix())
            canonical_path = Path(binding["canonical_path"])
            self.assertEqual(canonical_path, (root / relative).resolve(strict=True))
            canonical_bytes = canonical_path.read_bytes()
            self.assertEqual(binding["bytes"], len(canonical_bytes))
            self.assertEqual(binding["sha256"], integration.digest(canonical_bytes))
            self.assertEqual(binding["real_path"], binding["canonical_path"])
            self.assertEqual(binding["execution_path"], binding["canonical_path"])
            self.assertTrue(binding["version"])
        executed_commands = {
            command["id"]: command for command in executed_evidence["commands"]
        }
        self.assertEqual(
            executed_commands["frontend-build"]["resolved_argv"][0],
            str((root / integration.FRONTEND_TSC_RELATIVE).resolve(strict=True)),
        )
        self.assertEqual(
            executed_commands["component-build"]["resolved_argv"][0],
            str((root / integration.COMPONENT_TSC_RELATIVE).resolve(strict=True)),
        )
        self.assertEqual(
            executed_commands["component-tests"]["resolved_argv"][0],
            str((root / integration.COMPONENT_JEST_RELATIVE).resolve(strict=True)),
        )
        self.assertRegex(
            executed_evidence["receipt"]["started_at"],
            r"Z$",
        )
        self.assertGreaterEqual(executed_evidence["receipt"]["duration_ms"], 0)
        self.assertTrue(
            all(command["state"] == "PASSED" for command in executed_evidence["commands"])
        )
        self.assertTrue(
            all(
                Path(command["resolved_cwd"]).is_absolute()
                for command in executed_evidence["commands"]
            )
        )
        self.assertTrue(
            all(
                Path(command["resolved_argv"][0]).is_absolute()
                for command in executed_evidence["commands"]
            )
        )
        self.assertTrue(
            all(
                command["started_at"].endswith("Z")
                and command["ended_at"].endswith("Z")
                and command["duration_ms"] >= 0
                for command in executed_evidence["commands"]
            )
        )
        integration.check_install(root, source, archive)

        system_temp = Path(
            tempfile.mkdtemp(prefix="frontend-miniapp-closeout-system-temp-")
        )
        self.addCleanup(shutil.rmtree, system_temp, True)
        with mock.patch.object(integration.tempfile, "tempdir", str(system_temp)):
            closeout = integration.closeout_portable(root, source, archive)
        self.assertEqual(closeout["runtime_evidence_status"], "DECLARED")
        self.assertEqual(closeout["receipt_state_before"], "VERIFIED")
        self.assertEqual(closeout["receipt_state_after"], "ABSENT")
        self.assertFalse((root / integration.LOCAL_RECEIPT_ROOT_RELATIVE).exists())
        closeout_archive_root = Path(closeout["receipt_archive_root"])
        closeout_archive_path = Path(closeout["receipt_archive_path"])
        self.assertEqual(closeout_archive_root.parent, system_temp.resolve())
        self.assertEqual(stat.S_IMODE(closeout_archive_root.stat().st_mode), 0o700)
        self.assertTrue(closeout_archive_path.is_dir())
        self.assertIsNotNone(
            integration._assert_replaceable_receipt_bundle(closeout_archive_path)
        )
        portable_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(portable_manifest["runtime_evidence_status"], "DECLARED")
        integration.check_install(root, source, archive)

        with mock.patch.object(integration.tempfile, "tempdir", str(system_temp)):
            absent_closeout = integration.closeout_portable(root, source, archive)
        self.assertEqual(absent_closeout["receipt_state_before"], "ABSENT")
        self.assertEqual(absent_closeout["receipt_state_after"], "ABSENT")
        self.assertIsNone(absent_closeout["receipt_archive_root"])
        self.assertIsNone(absent_closeout["receipt_archive_path"])

    def test_local_receipt_digest_command_implementation_environment_and_count_drift_fail_closed(
        self,
    ) -> None:
        temporary, root, source, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)

        with self.subTest("receipt writer reservation"):
            destination = root / integration.LOCAL_RECEIPT_ROOT_RELATIVE
            destination.parent.mkdir(parents=True, exist_ok=True)
            with integration._reserve_local_receipt_bundle(destination) as reservation:
                lock = reservation.lock_parent_path / reservation.lock_name
                self.assertTrue(lock.is_file())
                with self.assertRaisesRegex(
                    integration.IntegrationError,
                    "reserved by another writer",
                ):
                    with integration._reserve_local_receipt_bundle(destination):
                        self.fail("a second receipt writer must never acquire the lock")
            self.assertTrue(lock.is_file())
            first_lock_identity = integration._directory_identity_from_stat(lock.stat())
            with integration._reserve_local_receipt_bundle(destination):
                self.assertEqual(
                    integration._directory_identity_from_stat(lock.stat()),
                    first_lock_identity,
                )
            self.assertIsNone(integration._assert_replaceable_receipt_bundle(destination))
            lock.unlink()

        with self.subTest("receipt writer lock identity is bound before commit"):
            lock_root = Path(
                tempfile.mkdtemp(prefix="frontend-miniapp-lock-binding-")
            )
            self.addCleanup(shutil.rmtree, lock_root, True)
            destination = lock_root / "receipt"
            displaced: Path | None = None
            competitor: Path | None = None
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "reservation identity drifted",
            ):
                with integration._reserve_local_receipt_bundle(destination) as reservation:
                    competitor = reservation.lock_parent_path / reservation.lock_name
                    displaced = competitor.with_name(f"{competitor.name}.held-by-test")
                    os.replace(competitor, displaced)
                    competitor.write_text("competitor lock must survive\n", encoding="utf-8")
                    reservation.assert_current("test commit preflight")
            self.assertIsNotNone(competitor)
            self.assertIsNotNone(displaced)
            assert competitor is not None
            assert displaced is not None
            self.assertEqual(
                competitor.read_text(encoding="utf-8"),
                "competitor lock must survive\n",
            )
            self.assertTrue(displaced.is_file())
            competitor.unlink()
            displaced.unlink()

        with self.subTest("bounded no-follow receipt reads bind the opened inode"):
            read_root = Path(tempfile.mkdtemp(prefix="frontend-miniapp-safe-read-"))
            self.addCleanup(shutil.rmtree, read_root, True)
            receipt_path = read_root / "receipt.json"
            held_path = read_root / "held-receipt.json"
            outside_path = read_root / "outside.json"
            receipt_path.write_text('{"owned":true}\n', encoding="utf-8")
            outside_path.write_text('{"competitor":true}\n', encoding="utf-8")

            def replace_opened_receipt() -> None:
                os.replace(receipt_path, held_path)
                receipt_path.symlink_to(outside_path)

            with self.assertRaisesRegex(
                integration.IntegrationError,
                "path identity drifted|changed while it was read",
            ):
                integration._read_bounded_regular_file(
                    read_root,
                    "receipt.json",
                    "receipt swap fixture",
                    1024,
                    after_open=replace_opened_receipt,
                )
            self.assertEqual(
                outside_path.read_text(encoding="utf-8"),
                '{"competitor":true}\n',
            )
            oversized = read_root / "oversized.log"
            oversized.write_bytes(b"x" * 17)
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "bounded regular file|byte limit",
            ):
                integration._read_bounded_regular_file(
                    read_root,
                    "oversized.log",
                    "oversized log fixture",
                    16,
                )
            bound_root = read_root / "bound-root"
            displaced_root = read_root / "displaced-bound-root"
            bound_root.mkdir()
            (bound_root / "receipt.json").write_text(
                '{"generation":1}\n',
                encoding="utf-8",
            )
            bound_identity = integration._directory_identity(
                bound_root,
                "bounded receipt root fixture",
            )
            os.replace(bound_root, displaced_root)
            bound_root.mkdir()
            (bound_root / "receipt.json").write_text(
                '{"generation":2}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "root identity drifted",
            ):
                integration._read_bounded_regular_file(
                    bound_root,
                    "receipt.json",
                    "replaced receipt root fixture",
                    1024,
                    expected_root_identity=bound_identity,
                )

        with self.subTest("receipt parent may not escape through a symlink"):
            containment = Path(
                tempfile.mkdtemp(prefix="frontend-miniapp-parent-containment-")
            )
            outside = Path(
                tempfile.mkdtemp(prefix="frontend-miniapp-parent-outside-")
            )
            self.addCleanup(shutil.rmtree, containment, True)
            self.addCleanup(shutil.rmtree, outside, True)
            (containment / "artifacts").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "unsafe directory component|path escapes",
            ):
                integration._ensure_relative_directory(
                    containment,
                    integration.LOCAL_RECEIPT_ROOT_RELATIVE.parent,
                    "receipt parent fixture",
                )

        with self.subTest("skipped and zero-pass summaries"):
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "complete no-skip run",
            ):
                integration._parse_test_counts(
                    "node-test",
                    "ℹ tests 4\nℹ pass 3\nℹ fail 0\nℹ skipped 1\n",
                    "skipped-fixture",
                )
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "counts are invalid|complete no-skip run",
            ):
                integration._parse_test_counts(
                    "node-test",
                    "ℹ tests 4\nℹ pass 0\nℹ fail 0\nℹ skipped 4\n",
                    "zero-pass-fixture",
                )
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "no successful summary",
            ):
                integration._parse_test_counts(
                    "unittest",
                    "Ran 4 tests in 1.000s\n\nOK (expected failures=1)\n",
                    "expected-failure-fixture",
                )

        with self.subTest("receipt digest"):
            receipt = self.write_valid_local_receipt(root)
            receipt["receipt_digest"] = "sha256:" + "0" * 64
            self.rewrite_receipt(root, receipt, recompute_digest=False)
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "receipt digest mismatch",
            ):
                integration.build_expected(source, archive, root)

        with self.subTest("command"):
            receipt = self.write_valid_local_receipt(root)
            commands = receipt["commands"]
            self.assertIsInstance(commands, list)
            commands[0]["command"] = "npm run build --unsafe"
            self.rewrite_receipt(root, receipt, recompute_digest=True)
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "command binding drifted",
            ):
                integration.build_expected(source, archive, root)

        with self.subTest("implementation"):
            receipt = self.write_valid_local_receipt(root)
            receipt["implementation_digest"] = "sha256:" + "1" * 64
            self.rewrite_receipt(root, receipt, recompute_digest=True)
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "implementation digest drifted",
            ):
                integration.build_expected(source, archive, root)

        with self.subTest("execution environment"):
            receipt = self.write_valid_local_receipt(root)
            environment = receipt["environment"]
            self.assertIsInstance(environment, dict)
            executables = environment["executables"]
            self.assertEqual(
                executables["python"]["path"],
                executables["python"]["canonical_path"],
            )
            executables["node"]["version"] += "-drifted"
            self.rewrite_receipt(root, receipt, recompute_digest=True)
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "execution environment drifted",
            ):
                integration.build_expected(source, archive, root)

        with self.subTest("schema Python environment binding"):
            receipt = self.write_valid_local_receipt(root)
            environment = receipt["environment"]
            self.assertIsInstance(environment, dict)
            variables = environment["variables"]
            variables["ELMOS_MINIAPP_SCHEMA_PYTHON"] = "/unbound/python3.11"
            self.rewrite_receipt(root, receipt, recompute_digest=True)
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "execution environment drifted",
            ):
                integration.build_expected(source, archive, root)

        with self.subTest("project tool canonical content binding"):
            receipt = self.write_valid_local_receipt(root)
            environment = receipt["environment"]
            self.assertIsInstance(environment, dict)
            executables = environment["executables"]
            executables["component_jest"]["sha256"] = "sha256:" + "2" * 64
            self.rewrite_receipt(root, receipt, recompute_digest=True)
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "execution environment drifted",
            ):
                integration.build_expected(source, archive, root)

        with self.subTest("command timing"):
            receipt = self.write_valid_local_receipt(root)
            commands = receipt["commands"]
            self.assertIsInstance(commands, list)
            commands[0]["duration_ms"] = -1
            self.rewrite_receipt(root, receipt, recompute_digest=True)
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "command duration_ms",
            ):
                integration.build_expected(source, archive, root)

        with self.subTest("test count"):
            receipt = self.write_valid_local_receipt(root)
            commands = receipt["commands"]
            self.assertIsInstance(commands, list)
            frontend_tests = next(
                command for command in commands if command["id"] == "frontend-tests"
            )
            frontend_tests["total_tests"] += 1
            frontend_tests["passed_tests"] += 1
            self.rewrite_receipt(root, receipt, recompute_digest=True)
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "test counts drifted",
            ):
                integration.build_expected(source, archive, root)

        with self.subTest("lower self-consistent exact count"):
            receipt = self.write_valid_local_receipt(root)
            commands = receipt["commands"]
            self.assertIsInstance(commands, list)
            frontend_tests = next(
                command for command in commands if command["id"] == "frontend-tests"
            )
            expected_frontend_count = next(
                command.expected_test_count
                for command in integration.LOCAL_QUALIFICATION_COMMANDS
                if command.command_id == "frontend-tests"
            )
            if expected_frontend_count is None:
                self.fail("frontend-tests qualification count must be exact")
            reduced_count = expected_frontend_count - 1
            reduced_output = (
                f"ℹ tests {reduced_count}\nℹ pass {reduced_count}\n"
                "ℹ fail 0\nℹ skipped 0\n"
            ).encode()
            log_path = (
                root
                / integration.LOCAL_RECEIPT_ROOT_RELATIVE
                / "logs/frontend-tests.log"
            )
            log_path.write_bytes(reduced_output)
            frontend_tests.update({
                "expected_test_count": reduced_count,
                "total_tests": reduced_count,
                "passed_tests": reduced_count,
                "failed_tests": 0,
                "skipped_tests": 0,
                "evidence": {
                    "path": (
                        integration.LOCAL_RECEIPT_ROOT_RELATIVE
                        / "logs/frontend-tests.log"
                    ).as_posix(),
                    "bytes": len(reduced_output),
                    "sha256": integration.digest(reduced_output),
                },
            })
            self.rewrite_receipt(root, receipt, recompute_digest=True)
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "exact test count drifted",
            ):
                integration.build_expected(source, archive, root)

    def test_refresh_is_all_tree_transactional_and_recovers_after_injected_failure(self) -> None:
        temporary, root, source, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        integration.write_install(root, source, archive)
        owned_destinations = [
            root / relative_root / name
            for relative_root in (
                integration.RUNTIME_RELATIVE,
                integration.WORKSPACE_RELATIVE,
            )
            for name in integration.EXPECTED_SKILLS
        ] + [root / integration.DOC_RELATIVE]
        before = {
            destination: integration._read_tree(destination)
            for destination in owned_destinations
        }

        with self.subTest("byte-identical destination inode swap fails before commit"):
            victim = owned_destinations[0]
            original = victim.with_name(f".{victim.name}-preflight-original")
            competitor_preserved = victim.with_name(
                f".{victim.name}-competitor-preserved"
            )
            swapped = False
            competitor_identity: integration.DirectoryIdentity | None = None

            def swap_after_preflight(
                stage: str,
                index: int,
                destination: Path,
            ) -> None:
                nonlocal swapped, competitor_identity
                if stage == "after_stage" and index == 0 and not swapped:
                    self.assertEqual(destination.resolve(), victim.resolve())
                    os.replace(victim, original)
                    shutil.copytree(original, victim, copy_function=shutil.copy2)
                    competitor_identity = integration._directory_identity(
                        victim,
                        "byte-identical competitor fixture",
                    )
                    swapped = True

            with self.assertRaisesRegex(
                integration.IntegrationError,
                "identity changed after preflight",
            ):
                integration.refresh_owned_install(
                    root,
                    source,
                    archive,
                    failure_injector=swap_after_preflight,
                )
            self.assertTrue(swapped)
            self.assertIsNotNone(competitor_identity)
            self.assertEqual(
                integration._directory_identity(
                    victim,
                    "preserved byte-identical competitor fixture",
                ),
                competitor_identity,
            )
            self.assertEqual(integration._read_tree(victim), before[victim])
            self.assertTrue(original.is_dir())
            os.replace(victim, competitor_preserved)
            os.replace(original, victim)
            self.assertTrue(competitor_preserved.is_dir())

        with self.subTest("byte-identical transaction backup inode swap is preserved"):
            victim = owned_destinations[0]
            victim_identity = integration._directory_identity(
                victim,
                "owned backup binding fixture",
            )
            original_backup = root / ".owned-backup-preserved-by-fixture"
            swapped_backup = False

            def swap_transaction_backup(
                stage: str,
                index: int,
                _destination: Path,
            ) -> None:
                nonlocal swapped_backup
                if stage == "after_backup" and index == 0 and not swapped_backup:
                    transaction_roots = list(
                        root.glob(".frontend-miniapp-refresh-transaction-*")
                    )
                    self.assertEqual(len(transaction_roots), 1)
                    backup = transaction_roots[0] / "backup/000"
                    os.replace(backup, original_backup)
                    shutil.copytree(
                        original_backup,
                        backup,
                        copy_function=shutil.copy2,
                    )
                    swapped_backup = True
                    raise RuntimeError("injected byte-identical backup inode replacement")

            with self.assertRaisesRegex(
                integration.IntegrationError,
                "rollback was incomplete",
            ):
                integration.refresh_owned_install(
                    root,
                    source,
                    archive,
                    failure_injector=swap_transaction_backup,
                )
            self.assertTrue(swapped_backup)
            self.assertEqual(
                integration._directory_identity(
                    original_backup,
                    "preserved original owned backup fixture",
                ),
                victim_identity,
            )
            self.assertEqual(integration._read_tree(original_backup), before[victim])
            recovery_roots = list(
                root.glob(".frontend-miniapp-refresh-recovery-*")
            )
            self.assertEqual(len(recovery_roots), 1)
            fake_backup = recovery_roots[0] / "000-backup"
            self.assertTrue(fake_backup.is_dir())
            self.assertNotEqual(
                integration._directory_identity(
                    fake_backup,
                    "preserved competing owned backup fixture",
                ),
                victim_identity,
            )
            self.assertEqual(integration._read_tree(fake_backup), before[victim])
            self.assertFalse(victim.exists())
            os.replace(original_backup, victim)
            shutil.rmtree(recovery_roots[0])
            self.assertEqual(
                integration._directory_identity(
                    victim,
                    "restored owned backup fixture",
                ),
                victim_identity,
            )

        self.write_valid_local_receipt(root)

        def inject(stage: str, index: int, _destination: Path) -> None:
            if stage == "after_commit" and index == 3:
                raise RuntimeError("injected transactional refresh failure")

        with self.assertRaisesRegex(RuntimeError, "injected transactional"):
            integration.refresh_owned_install(
                root,
                source,
                archive,
                failure_injector=inject,
            )
        for destination, original_tree in before.items():
            self.assertEqual(
                integration._read_tree(destination),
                original_tree,
                destination,
            )
        self.assertEqual(
            list(root.glob(".frontend-miniapp-refresh-transaction-*")),
            [],
        )

        recovered = integration.refresh_owned_install(root, source, archive)
        self.assertEqual(
            recovered["manifest"]["runtime_evidence_status"],
            "LOCAL_EXECUTED",
        )
        integration.check_install(root, source, archive)

        with self.subTest("portable closeout restores exact receipt after refresh failure"):
            receipt_destination = root / integration.LOCAL_RECEIPT_ROOT_RELATIVE
            receipt_identity = integration._assert_replaceable_receipt_bundle(
                receipt_destination
            )
            self.assertIsNotNone(receipt_identity)
            closeout_system_temp = Path(
                tempfile.mkdtemp(prefix="frontend-miniapp-closeout-rollback-temp-")
            )
            self.addCleanup(shutil.rmtree, closeout_system_temp, True)

            def fail_portable_refresh(
                stage: str,
                index: int,
                _destination: Path,
            ) -> None:
                if stage == "after_commit" and index == 3:
                    raise RuntimeError("injected portable closeout refresh failure")

            with mock.patch.object(
                integration.tempfile,
                "tempdir",
                str(closeout_system_temp),
            ), self.assertRaisesRegex(
                integration.IntegrationError,
                "receipt_restored=True",
            ):
                integration.closeout_portable(
                    root,
                    source,
                    archive,
                    failure_injector=fail_portable_refresh,
                )
            self.assertEqual(
                integration._assert_replaceable_receipt_bundle(receipt_destination),
                receipt_identity,
            )
            closeout_archives = list(
                closeout_system_temp.glob(
                    "elmos-frontend-miniapp-portable-closeout-*"
                )
            )
            self.assertEqual(len(closeout_archives), 1)
            self.assertEqual(list(closeout_archives[0].iterdir()), [])
            integration.check_install(root, source, archive)

        with self.subTest("portable closeout never overwrites a competing receipt"):
            receipt_destination = root / integration.LOCAL_RECEIPT_ROOT_RELATIVE
            receipt_identity = integration._assert_replaceable_receipt_bundle(
                receipt_destination
            )
            self.assertIsNotNone(receipt_identity)
            closeout_system_temp = Path(
                tempfile.mkdtemp(prefix="frontend-miniapp-closeout-competitor-temp-")
            )
            self.addCleanup(shutil.rmtree, closeout_system_temp, True)
            competitor_created = False

            def create_receipt_competitor(
                stage: str,
                index: int,
                _destination: Path,
            ) -> None:
                nonlocal competitor_created
                if stage == "after_commit" and index == 3 and not competitor_created:
                    receipt_destination.mkdir()
                    (receipt_destination / "owner.txt").write_text(
                        "competitor must survive portable closeout rollback\n",
                        encoding="utf-8",
                    )
                    competitor_created = True
                    raise RuntimeError("injected competing receipt destination")

            with mock.patch.object(
                integration.tempfile,
                "tempdir",
                str(closeout_system_temp),
            ), self.assertRaisesRegex(
                integration.IntegrationError,
                "receipt_restored=False",
            ):
                integration.closeout_portable(
                    root,
                    source,
                    archive,
                    failure_injector=create_receipt_competitor,
                )
            self.assertTrue(competitor_created)
            self.assertEqual(
                (receipt_destination / "owner.txt").read_text(encoding="utf-8"),
                "competitor must survive portable closeout rollback\n",
            )
            closeout_archives = list(
                closeout_system_temp.glob(
                    "elmos-frontend-miniapp-portable-closeout-*"
                )
            )
            self.assertEqual(len(closeout_archives), 1)
            archived_receipt = (
                closeout_archives[0] / integration.LOCAL_RECEIPT_ROOT_RELATIVE.name
            )
            self.assertEqual(
                integration._assert_replaceable_receipt_bundle(archived_receipt),
                receipt_identity,
            )
            shutil.rmtree(receipt_destination)
            os.replace(archived_receipt, receipt_destination)
            self.assertEqual(
                integration._assert_replaceable_receipt_bundle(receipt_destination),
                receipt_identity,
            )
            integration.check_install(root, source, archive)

        unowned = owned_destinations[0] / "user-note.txt"
        unowned.write_text("must survive a refused refresh\n", encoding="utf-8")
        with self.assertRaisesRegex(integration.IntegrationError, "path drift"):
            integration.refresh_owned_install(root, source, archive)
        self.assertEqual(
            unowned.read_text(encoding="utf-8"),
            "must survive a refused refresh\n",
        )

        unowned.unlink()
        identical_drift_paths = [
            root
            / relative_root
            / integration.EXPECTED_SKILLS[0]
            / "agents/openai.yaml"
            for relative_root in (
                integration.RUNTIME_RELATIVE,
                integration.WORKSPACE_RELATIVE,
            )
        ]
        for path in identical_drift_paths:
            path.write_bytes(path.read_bytes() + b"identical user drift\n")
        with self.assertRaisesRegex(
            integration.IntegrationError,
            "prior installed tree digests drifted",
        ):
            integration.refresh_owned_install(root, source, archive)
        for path in identical_drift_paths:
            self.assertTrue(path.read_bytes().endswith(b"identical user drift\n"))

    def test_check_detects_content_and_mode_drift(self) -> None:
        temporary, root, source, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        integration.write_install(root, source, archive)
        drifted = (
            root
            / integration.RUNTIME_RELATIVE
            / integration.EXPECTED_SKILLS[0]
            / "agents/openai.yaml"
        )
        drifted.write_bytes(drifted.read_bytes() + b"drift\n")
        drifted.chmod(0o755)

        with self.assertRaisesRegex(integration.IntegrationError, "already drifted"):
            integration.refresh_owned_install(root, source, archive)

        with self.assertRaisesRegex(integration.IntegrationError, "installation drifted"):
            integration.check_install(root, source, archive)
        with self.assertRaisesRegex(integration.IntegrationError, "refusing to overwrite"):
            integration.write_install(root, source, archive)

    def test_write_refuses_unowned_skill_collision(self) -> None:
        temporary, root, source, archive = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        collision = (
            root
            / integration.RUNTIME_RELATIVE
            / "frontend-to-miniapp-orchestrator"
        )
        collision.mkdir(parents=True)
        (collision / "SKILL.md").write_text("user owned\n", encoding="utf-8")

        with self.assertRaisesRegex(integration.IntegrationError, "unowned or drifted"):
            integration.write_install(root, source, archive)
        self.assertEqual(
            (collision / "SKILL.md").read_text(encoding="utf-8"), "user owned\n"
        )

        with self.subTest("first install never replaces a competing directory"):
            reservation_root = Path(
                tempfile.mkdtemp(prefix="frontend-miniapp-first-install-")
            )
            self.addCleanup(shutil.rmtree, reservation_root, True)
            destination = reservation_root / "new-skill"
            tree = {
                "SKILL.md": integration.FilePayload(b"generated\n"),
            }

            def create_competitor(path: Path) -> None:
                path.mkdir()
                (path / "owner.txt").write_text(
                    "competitor must survive\n",
                    encoding="utf-8",
                )

            with self.assertRaisesRegex(
                integration.IntegrationError,
                "appeared concurrently",
            ):
                integration._write_tree(
                    destination,
                    tree,
                    before_reserve=create_competitor,
                )
            self.assertEqual(
                (destination / "owner.txt").read_text(encoding="utf-8"),
                "competitor must survive\n",
            )
            self.assertFalse((destination / "SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
