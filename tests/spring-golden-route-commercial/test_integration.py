from __future__ import annotations

import hashlib
import shutil
import stat
import sys
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tooling"))

import integrate_spring_golden_route_commercial_skills as integration  # noqa: E402
import skill_creator_tools  # noqa: E402


class SpringGoldenRouteIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.archive = ROOT / integration.ARCHIVE_RELATIVE
        cls.summary = integration.validate_source(cls.archive)
        cls.expected = integration.build_expected(cls.summary)

    def test_pinned_source_inventory_and_dependency_graphs(self) -> None:
        self.assertEqual(integration.EXPECTED_ARCHIVE_ENTRY_COUNT, len(self.summary["records"]))
        self.assertEqual(integration.EXPECTED_SKILLS, self.summary["skill_count"])
        self.assertEqual(integration.EXPECTED_CONTRACTS, self.summary["contract_count"])
        self.assertEqual(
            integration.EXPECTED_DEPENDENCY_EDGES,
            self.summary["dependency_edge_count"],
        )
        self.assertEqual(
            integration.EXPECTED_FOUNDATION_CRITICAL_EDGES,
            self.summary["foundation_critical_dependency_edge_count"],
        )
        self.assertEqual(
            integration.EXPECTED_SKILLS,
            len(self.summary["topological_order"]),
        )
        position = {
            name: index for index, name in enumerate(self.summary["topological_order"])
        }
        for record in self.summary["skills"]:
            name = record["entry"]["name"]
            for dependency in record["entry"].get("dependencies", []):
                self.assertLess(position[dependency], position[name])

    def test_expected_install_is_dual_root_and_fail_closed(self) -> None:
        files = self.expected["files"]
        self.assertEqual(integration.EXPECTED_SKILLS * 10 + 3, len(files))
        self.assertEqual(
            {
                "implementation_state": "SPECIFICATION_IMPORTED",
                "runtime_evidence_status": "NOT_RUN",
                "customer_evidence_status": "NOT_RUN",
                "external_evidence_status": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
                "side_effects_authorized": False,
            },
            {
                key: self.expected["manifest"][key]
                for key in (
                    "implementation_state",
                    "runtime_evidence_status",
                    "customer_evidence_status",
                    "external_evidence_status",
                    "certification",
                    "side_effects_authorized",
                )
            },
        )
        self.assertEqual(5, len(self.expected["manifest"]["quarantined_archive_members"]))
        self.assertTrue(
            all(
                "__pycache__" in member and member.endswith(".pyc")
                for member in self.expected["manifest"]["quarantined_archive_members"]
            )
        )
        registry = self.expected["runtime_registry"]
        self.assertEqual(integration.EXPECTED_SKILLS, registry["skill_count"])
        self.assertEqual(integration.EXPECTED_SKILLS, len(registry["bindings"]))
        self.assertEqual("BOUNDED_LOCAL_CONTROL_PLANE_IMPLEMENTED", registry["binding_state"])
        self.assertEqual("NOT_RUN", registry["domain_runtime_evidence_status"])
        self.assertEqual("NOT_CERTIFIED", registry["certification"])
        for name in self.expected["skill_names"]:
            runtime = integration.RUNTIME_RELATIVE / name
            workspace = integration.WORKSPACE_RELATIVE / name
            for relative in (
                Path("SKILL.md"),
                Path("agents/openai.yaml"),
                Path("references/contract.json"),
                Path("references/runtime-binding.json"),
                Path("schemas/skill-contract.schema.json"),
            ):
                self.assertEqual(
                    files[runtime / relative].data,
                    files[workspace / relative].data,
                )
            self.assertFalse(any("scripts" in path.parts for path in files if name in path.parts))

    def test_repository_install_matches_skill_creator_contract(self) -> None:
        result = integration.check_install(ROOT, self.expected)
        self.assertEqual("SPECIFICATION_IMPORTED", result["decision"])
        for name in self.expected["skill_names"]:
            for base in (integration.RUNTIME_RELATIVE, integration.WORKSPACE_RELATIVE):
                valid, reason = skill_creator_tools.validate_skill(ROOT / base / name)
                self.assertTrue(valid, f"{base / name}: {reason}")

    def test_full_install_is_preflighted_idempotent_and_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / integration.ARCHIVE_RELATIVE
            archive.parent.mkdir(parents=True)
            shutil.copy2(self.archive, archive)

            first = integration.integrate(root, write=True)
            second = integration.integrate(root, write=True)
            checked = integration.integrate(root, write=False)
            self.assertEqual(first, second)
            self.assertEqual(first, checked)
            self.assertEqual("SPECIFICATION_IMPORTED", checked["decision"])

            for name in self.expected["skill_names"]:
                runtime = integration._read_tree(root, integration.RUNTIME_RELATIVE / name)
                workspace = integration._read_tree(root, integration.WORKSPACE_RELATIVE / name)
                self.assertEqual(runtime, workspace)
                self.assertEqual(
                    {
                        "SKILL.md",
                        "agents/openai.yaml",
                        "references/contract.json",
                        "references/runtime-binding.json",
                        "schemas/skill-contract.schema.json",
                    },
                    set(runtime),
                )

                contract = runtime["references/contract.json"]
                schema = runtime["schemas/skill-contract.schema.json"]
                binding = runtime["references/runtime-binding.json"]
                self.assertEqual(
                    self.summary["records"][f"contracts/{name}.json"].data,
                    contract,
                )
                self.assertEqual(
                    self.summary["records"]["schemas/skill-contract.schema.json"].data,
                    schema,
                )
                self.assertIn(b'"supported_operations": [', binding)
                self.assertIn(b'"domain_runtime_evidence_status": "NOT_RUN"', binding)

    def test_destination_collision_blocks_before_any_generated_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            name = self.expected["skill_names"][0]
            collision = root / integration.RUNTIME_RELATIVE / name / "SKILL.md"
            collision.parent.mkdir(parents=True)
            collision.write_bytes(b"user-owned content\n")

            with self.assertRaisesRegex(
                integration.IntegrationError,
                "refusing to overwrite different destination",
            ):
                integration.write_install(root, self.expected)

            self.assertEqual(b"user-owned content\n", collision.read_bytes())
            self.assertFalse(
                (root / integration.DOC_RELATIVE / "installed-manifest.json").exists()
            )
            self.assertFalse((root / integration.WORKSPACE_RELATIVE / name).exists())

    def test_destination_parent_symlink_cannot_escape_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repository"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "agent-skills").symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(
                integration.IntegrationError,
                "symlink in destination path",
            ):
                integration.write_install(root, self.expected)

            self.assertEqual([], list(outside.iterdir()))

    def test_atomic_publish_never_overwrites_a_concurrent_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "artifact.json"
            target.write_bytes(b"concurrent owner\n")
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "destination appeared during write",
            ):
                integration._write_atomic(
                    target,
                    integration.FilePayload(b"generated\n"),
                )
            self.assertEqual(b"concurrent owner\n", target.read_bytes())

    def test_generated_mode_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            relative, payload = next(iter(self.expected["files"].items()))
            target = root / relative
            target.parent.mkdir(parents=True)
            target.write_bytes(payload.data)
            target.chmod(0o755)
            with self.assertRaisesRegex(
                integration.IntegrationError,
                "generated destination mode mismatch",
            ):
                integration._preflight(root, self.expected)

    def test_interrupted_per_file_install_is_resumable(self) -> None:
        name = self.expected["skill_names"][0]
        prefixes = (
            integration.RUNTIME_RELATIVE / name,
            integration.WORKSPACE_RELATIVE / name,
        )
        files = {
            path: payload
            for path, payload in self.expected["files"].items()
            if any(path.is_relative_to(prefix) for prefix in prefixes)
        }
        expected = {
            "files": files,
            "skill_names": [name],
            "manifest": {"dependency_edge_count": 0},
            "compiled_contracts": {"contracts": [{}]},
        }
        original = integration._write_atomic
        calls = 0

        def fail_second(path: Path, payload: integration.FilePayload) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected interruption")
            original(path, payload)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(integration, "_write_atomic", side_effect=fail_second):
                with self.assertRaisesRegex(OSError, "injected interruption"):
                    integration.write_install(root, expected)

            self.assertEqual(1, sum(path.is_file() for path in root.rglob("*")))
            result = integration.write_install(root, expected)
            self.assertEqual("SPECIFICATION_IMPORTED", result["decision"])
            self.assertEqual(set(files), {path.relative_to(root) for path in root.rglob("*") if path.is_file()})

    def test_tampered_archive_and_checksum_bound_record_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "tampered.zip"
            payload = bytearray(self.archive.read_bytes())
            payload[len(payload) // 2] ^= 1
            archive.write_bytes(payload)
            with self.assertRaisesRegex(integration.IntegrationError, "archive SHA-256 mismatch"):
                integration.inspect_archive(archive)

        records = dict(self.summary["records"])
        contract_path = next(
            relative for relative in records if relative.startswith("contracts/")
        )
        record = records[contract_path]
        tampered = record.data + b"\n"
        records[contract_path] = replace(
            record,
            data=tampered,
            size=len(tampered),
            sha256=hashlib.sha256(tampered).hexdigest(),
        )
        with self.assertRaisesRegex(integration.IntegrationError, "outer checksum mismatch"):
            integration.validate_source(records)

    def test_zip_path_escape_and_symlink_are_rejected(self) -> None:
        cases = (
            ("pkg/../escape.txt", stat.S_IFREG | 0o644, "escaping archive path"),
            ("pkg//ambiguous.txt", stat.S_IFREG | 0o644, "non-canonical archive path"),
            ("pkg/link", stat.S_IFLNK | 0o777, "non-regular ZIP entry"),
        )
        for member, mode, message in cases:
            with self.subTest(member=member), tempfile.TemporaryDirectory() as temporary:
                archive = Path(temporary) / "unsafe.zip"
                info = zipfile.ZipInfo(member)
                info.create_system = 3
                info.external_attr = mode << 16
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
                    handle.writestr(info, b"payload")
                with self.assertRaisesRegex(integration.IntegrationError, message):
                    integration.inspect_archive(
                        archive,
                        trusted_sha256=None,
                        expected_entry_count=None,
                        expected_total_bytes=None,
                        expected_mode_counts=None,
                        expected_root="pkg",
                    )


if __name__ == "__main__":
    unittest.main()
