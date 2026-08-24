from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unicodedata
import unittest
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLING_ROOT = REPOSITORY_ROOT / "tooling"
if str(TOOLING_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLING_ROOT))

import integrate_elmos_7plus1_skills as integration


class ElmosSevenPlusOneIntegrationTest(unittest.TestCase):
    def temporary_repository(
        self,
    ) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary = tempfile.TemporaryDirectory(prefix="elmos-7plus1-integration-")
        root = Path(temporary.name)
        archive_directory = root / integration.ARCHIVE_DIRECTORY_RELATIVE
        archive_directory.mkdir(parents=True)
        for spec in integration.PACKAGE_SPECS:
            shutil.copy2(
                REPOSITORY_ROOT
                / integration.ARCHIVE_DIRECTORY_RELATIVE
                / spec.archive_name,
                archive_directory / spec.archive_name,
            )
        for relative in integration.RUNTIME_ARTIFACTS:
            source = REPOSITORY_ROOT / relative
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        return temporary, root, archive_directory

    def rewrite_archive(
        self,
        source: Path,
        destination: Path,
        *,
        replacements: dict[str, bytes] | None = None,
        additions: dict[str, bytes] | None = None,
    ) -> None:
        replacements = replacements or {}
        additions = additions or {}
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source, "r") as source_zip, zipfile.ZipFile(
            destination, "w"
        ) as target_zip:
            observed: set[str] = set()
            for source_info in source_zip.infolist():
                observed.add(source_info.filename)
                target_info = copy.copy(source_info)
                target_info.flag_bits &= ~0x1
                payload = replacements.get(
                    source_info.filename, source_zip.read(source_info)
                )
                target_zip.writestr(target_info, payload)
            unknown_replacements = set(replacements) - observed
            if unknown_replacements:
                raise AssertionError(
                    f"test tried to replace absent members: {unknown_replacements}"
                )
            for relative, payload in additions.items():
                info = zipfile.ZipInfo(relative)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                target_zip.writestr(info, payload)

    def rewritten_package(
        self,
        temporary: Path,
        spec: integration.PackageSpec,
        replacements: dict[str, bytes],
        *,
        additions: dict[str, bytes] | None = None,
    ) -> Path:
        source = (
            REPOSITORY_ROOT
            / integration.ARCHIVE_DIRECTORY_RELATIVE
            / spec.archive_name
        )
        destination = temporary / spec.archive_name
        self.rewrite_archive(
            source,
            destination,
            replacements=replacements,
            additions=additions,
        )
        return destination

    def test_exact_archive_identity_union_and_source_skill_inventory(self) -> None:
        snapshot = integration.validate_archives(
            REPOSITORY_ROOT / integration.ARCHIVE_DIRECTORY_RELATIVE
        )

        self.assertEqual(len(snapshot.packages), 8)
        self.assertEqual(
            sum(package.entry_count for package in snapshot.packages), 469
        )
        self.assertEqual(len(snapshot.canonical_files), 252)
        self.assertEqual(len(snapshot.source_skills), 101)
        self.assertEqual(
            sum(skill.role == "package-orchestrator" for skill in snapshot.source_skills),
            8,
        )
        self.assertEqual(
            sum(skill.role == "child" for skill in snapshot.source_skills), 93
        )
        self.assertEqual(
            [package.archive_sha256 for package in snapshot.packages],
            [spec.archive_sha256 for spec in integration.PACKAGE_SPECS],
        )
        self.assertEqual(
            [package.entry_count for package in snapshot.packages],
            [55, 60, 59, 59, 59, 59, 59, 59],
        )
        self.assertEqual(
            snapshot.package_topological_order,
            ("P00", "P01", "P02", "P05", "P03", "P06", "P04", "P07"),
        )
        names = [skill.source_name for skill in snapshot.source_skills]
        self.assertEqual(len(names), len(set(names)))
        self.assertLessEqual(max(map(len, names)), 64)
        self.assertNotIn(integration.ROOT_SKILL_NAME, names)
        for generated_root_member in (
            "SKILL.md",
            "README.md",
            "manifest.json",
            "ELMOS_WORKFLOW.md",
            "CHANGELOG.md",
        ):
            self.assertNotIn(generated_root_member, snapshot.canonical_files)

    def test_path_member_and_zip_bomb_guards_fail_closed(self) -> None:
        unsafe_paths = (
            "../escape",
            "/absolute",
            "package\\escape",
            "package/./ambiguous",
            "package/NUL.txt",
            "package/trailing. ",
            "package/has\x00nul",
            "package/" + unicodedata.normalize("NFD", "é") + ".md",
        )
        for relative in unsafe_paths:
            with self.subTest(relative=relative):
                with self.assertRaises(integration.IntegrationError):
                    integration._validated_relative_path(relative, "test")

        encrypted = zipfile.ZipInfo("package/file.txt")
        encrypted.flag_bits |= 0x1
        encrypted.create_system = 3
        encrypted.external_attr = (stat.S_IFREG | 0o644) << 16
        with self.assertRaisesRegex(integration.IntegrationError, "encrypted"):
            integration._validate_member_metadata(encrypted)

        symlink = zipfile.ZipInfo("package/link")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(integration.IntegrationError, "link or special"):
            integration._validate_member_metadata(symlink)

        bomb = zipfile.ZipInfo("package/bomb")
        bomb.create_system = 3
        bomb.external_attr = (stat.S_IFREG | 0o644) << 16
        bomb.file_size = integration.MAX_ARCHIVE_ENTRY_BYTES + 1
        bomb.compress_size = 1
        with self.assertRaisesRegex(integration.IntegrationError, "size is unsafe"):
            integration._validate_member_metadata(bomb)

    def test_archive_casefold_duplicate_is_rejected(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="elmos-7plus1-casefold-")
        self.addCleanup(temporary.cleanup)
        archive = Path(temporary.name) / "collision.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            for relative in ("package/File.txt", "package/file.txt"):
                info = zipfile.ZipInfo(relative)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                handle.writestr(info, b"same\n")

        with self.assertRaisesRegex(
            integration.IntegrationError, "case/Unicode archive path collision"
        ):
            integration.inspect_archive(archive)

    def test_unknown_archive_member_is_rejected(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="elmos-7plus1-unknown-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        spec = integration.PACKAGE_SPECS[0]
        archive = self.rewritten_package(
            root,
            spec,
            {},
            additions={f"{spec.archive_root}/unexpected.txt": b"unknown\n"},
        )

        with self.assertRaisesRegex(integration.IntegrationError, "unknown="):
            integration.validate_archive(
                archive, spec, verify_archive_identity=False
            )

    def test_manifest_version_subskill_name_and_dag_drift_are_rejected(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="elmos-7plus1-semantic-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        spec = integration.PACKAGE_SPECS[1]
        original = (
            REPOSITORY_ROOT
            / integration.ARCHIVE_DIRECTORY_RELATIVE
            / spec.archive_name
        )
        manifest_path = f"{spec.archive_root}/manifest.json"
        with zipfile.ZipFile(original, "r") as handle:
            manifest = json.loads(handle.read(manifest_path).decode("utf-8"))
            root_skill = handle.read(f"{spec.archive_root}/SKILL.md")

        mutations: list[tuple[str, dict[str, bytes], str]] = []
        dependency_manifest = dict(manifest)
        dependency_manifest["dependencies"] = ["P07"]
        mutations.append(
            (
                "dependency",
                {manifest_path: json.dumps(dependency_manifest).encode("utf-8")},
                "dependency DAG mismatch",
            )
        )
        subskill_manifest = dict(manifest)
        subskill_manifest["subskills"] = list(manifest["subskills"][:-1])
        mutations.append(
            (
                "subskill",
                {manifest_path: json.dumps(subskill_manifest).encode("utf-8")},
                "subskills",
            )
        )
        mutations.append(
            (
                "version",
                {"VERSION": b"9.9.9\n"},
                "VERSION mismatch",
            )
        )
        mutations.append(
            (
                "skill-name",
                {
                    f"{spec.archive_root}/SKILL.md": root_skill.replace(
                        f"name: {spec.name}".encode("utf-8"),
                        b"name: elmos-wrong-package-name",
                        1,
                    )
                },
                "Skill name",
            )
        )

        for label, replacements, message in mutations:
            with self.subTest(label=label):
                archive = self.rewritten_package(
                    root / label, spec, replacements
                )
                with self.assertRaisesRegex(integration.IntegrationError, message):
                    integration.validate_archive(
                        archive, spec, verify_archive_identity=False
                    )

        with self.assertRaisesRegex(integration.IntegrationError, "cycle"):
            integration.validate_package_graph(
                {"P00": ("P01",), "P01": ("P00",)}
            )

    def test_shared_file_mismatch_is_never_silently_merged(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="elmos-7plus1-shared-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        first_spec = integration.PACKAGE_SPECS[0]
        second_spec = integration.PACKAGE_SPECS[1]
        first_archive = (
            REPOSITORY_ROOT
            / integration.ARCHIVE_DIRECTORY_RELATIVE
            / first_spec.archive_name
        )
        second_source = (
            REPOSITORY_ROOT
            / integration.ARCHIVE_DIRECTORY_RELATIVE
            / second_spec.archive_name
        )
        with zipfile.ZipFile(second_source, "r") as handle:
            agents = handle.read("AGENTS.md")
        second_archive = self.rewritten_package(
            root,
            second_spec,
            {"AGENTS.md": agents + b"\nMISMATCH\n"},
        )
        first = integration.validate_archive(
            first_archive, first_spec, verify_archive_identity=False
        )
        second = integration.validate_archive(
            second_archive, second_spec, verify_archive_identity=False
        )

        with self.assertRaisesRegex(integration.IntegrationError, "shared file mismatch"):
            integration.merge_source_trees((first, second))

    def test_archive_scripts_are_data_and_are_not_executed(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="elmos-7plus1-script-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        marker = root / "archive-script-executed"
        spec = integration.PACKAGE_SPECS[0]
        payload = (
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
        ).encode("utf-8")
        archive = self.rewritten_package(
            root,
            spec,
            {"scripts/score_readiness.py": payload},
        )

        snapshot = integration.validate_archive(
            archive, spec, verify_archive_identity=False
        )
        self.assertFalse(marker.exists())
        self.assertEqual(
            snapshot.files["scripts/score_readiness.py"].content, payload
        )

    def test_archive_skill_instructions_never_enter_active_wrappers(self) -> None:
        temporary, root, archive_directory = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        spec = integration.PACKAGE_SPECS[0]
        child = spec.subskills[0]
        source_member = f"{spec.archive_root}/skills/{child}/SKILL.md"
        source_archive = REPOSITORY_ROOT / integration.ARCHIVE_DIRECTORY_RELATIVE / spec.archive_name
        with zipfile.ZipFile(source_archive, "r") as handle:
            original = handle.read(source_member)
        adversarial_description = b"ARCHIVE_DESCRIPTION_MUST_NOT_APPEAR"
        adversarial_body = b"ARCHIVE_BODY_MUST_NOT_APPEAR"
        description_start = original.index(b"description: ")
        description_end = original.index(b"\n", description_start)
        mutated = (
            original[:description_start]
            + b"description: "
            + adversarial_description
            + original[description_end:]
            + b"\n"
            + adversarial_body
            + b"\n"
        )
        self.rewrite_archive(
            source_archive,
            archive_directory / spec.archive_name,
            replacements={source_member: mutated},
        )

        snapshot = integration.install_integration(
            root, archive_directory, verify_archive_identity=False
        )
        source_bytes = (
            root
            / integration.SOURCE_RELATIVE
            / integration._materialized_source_path(source_member)
        ).read_bytes()
        self.assertIn(adversarial_description, source_bytes)
        self.assertIn(adversarial_body, source_bytes)
        skill_name = f"elmos-{child}"
        for install_root in integration.INSTALL_ROOTS:
            active = (root / install_root / skill_name / "SKILL.md").read_bytes()
            self.assertNotIn(adversarial_description, active)
            self.assertNotIn(adversarial_body, active)
            self.assertIn(b"This active Skill is repository-authored", active)
        self.assertEqual(len(snapshot.source_skills), 101)

    def test_runtime_registries_and_artifacts_fail_closed_without_execution(self) -> None:
        cases = (
            "missing",
            "extra",
            "mode-drift",
            "public-extra",
            "public-drift",
            "public-action-drift",
            "adapter-union-drift",
        )
        for case in cases:
            with self.subTest(case=case):
                temporary, root, archive_directory = self.temporary_repository()
                self.addCleanup(temporary.cleanup)
                if case == "missing":
                    missing = root / integration.RUNTIME_ARTIFACTS[0]
                    missing.rename(missing.with_suffix(".missing"))
                    message = "required runtime artifact"
                elif case in {"extra", "mode-drift"}:
                    registry_path = root / integration.RUNTIME_CAPABILITY_REGISTRY
                    document = json.loads(registry_path.read_text(encoding="utf-8"))
                    if case == "extra":
                        extra = dict(document["capabilities"][0])
                        extra["skill_name"] = "elmos-unowned-extra-skill"
                        document["capabilities"].append(extra)
                        message = "exactly 102"
                    else:
                        row = next(
                            item for item in document["capabilities"] if item["mode"] == "local"
                        )
                        row["mode"] = "requires_adapter"
                        message = "action/mode is incoherent"
                    registry_path.write_text(
                        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                elif case in {"public-extra", "public-drift", "public-action-drift"}:
                    registry_path = root / integration.RUNTIME_PUBLIC_METHOD_REGISTRY
                    document = json.loads(registry_path.read_text(encoding="utf-8"))
                    if case == "public-extra":
                        extra = dict(document["methods"][0])
                        extra["method"] = "Unowned.extra"
                        document["methods"].append(extra)
                        message = "exactly 50"
                    elif case == "public-drift":
                        document["methods"][0]["domain_errors"] = []
                        message = "domain_errors are invalid"
                    else:
                        document["methods"][0]["action"] = "compile-workflow"
                        message = "pinned digest mismatch"
                    registry_path.write_text(
                        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                else:
                    registry_path = root / integration.RUNTIME_SKILL_REGISTRY
                    document = json.loads(registry_path.read_text(encoding="utf-8"))
                    package = document["packages"][0]
                    package["adapter_actions"] = package["adapter_actions"][1:]
                    message = "action/mode is incoherent|requires_adapter union"
                    registry_path.write_text(
                        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                with self.assertRaisesRegex(integration.IntegrationError, message):
                    integration.install_integration(root, archive_directory)
                self.assertFalse((root / integration.SOURCE_RELATIVE).exists())

        temporary, root, archive_directory = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        integration.install_integration(root, archive_directory)
        module = root / "engines/software-factory-engine/src/elmos_software_factory/handlers.py"
        module.write_bytes(module.read_bytes() + b"\n# digest drift\n")
        with self.assertRaisesRegex(integration.IntegrationError, "drifted"):
            integration.check_integration(root, archive_directory)

    def test_install_check_wrappers_and_conservative_statuses(self) -> None:
        temporary, root, archive_directory = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        seeded_docs = root / integration.DOC_RELATIVE
        seeded_docs.mkdir(parents=True)
        (seeded_docs / "README.md").write_bytes(integration._render_docs_readme())

        snapshot = integration.install_integration(root, archive_directory)
        checked = integration.check_integration(root, archive_directory)
        self.assertEqual(
            snapshot.package_topological_order, checked.package_topological_order
        )
        expected = integration.build_expected(snapshot, root)
        self.assertEqual(len(expected["skill_trees"]), 102)

        canonical = root / integration.SOURCE_RELATIVE
        self.assertEqual(len(integration._read_tree(canonical)), 252)
        self.assertEqual(list(canonical.rglob("SKILL.md")), [])
        self.assertFalse((canonical / "manifest.json").exists())
        self.assertEqual(list(canonical.rglob("AGENTS.md")), [])
        neutralized_agents = canonical / integration.NEUTRALIZED_SOURCE_PATHS["AGENTS.md"]
        self.assertEqual(
            neutralized_agents.read_bytes(), snapshot.canonical_files["AGENTS.md"].content
        )

        manifest_path = root / integration.DOC_RELATIVE / "installed-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        compiled_manifest = json.loads(
            (root / integration.DOC_RELATIVE / "compiled-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["source_archive_count"], 8)
        self.assertEqual(manifest["source_archive_entry_count"], 469)
        self.assertEqual(manifest["canonical_source_file_count"], 252)
        self.assertEqual(manifest["source_skill_count"], 101)
        self.assertEqual(manifest["installed_skill_count_per_root"], 102)
        self.assertEqual(
            {
                row["source_name"]: row["installed_name"]
                for row in manifest["installed_name_resolutions"]
            },
            integration.INSTALLED_NAME_OVERRIDES,
        )
        self.assertEqual(
            compiled_manifest["installed_name_resolutions"],
            manifest["installed_name_resolutions"],
        )
        self.assertEqual(
            manifest["repo_owned_root_skill"], integration.ROOT_SKILL_NAME
        )
        self.assertFalse(manifest["repo_owned_root_is_archive_member"])
        self.assertEqual(
            manifest["implementation_states"],
            {
                integration.BLUEPRINT_IMPORTED: 101,
                integration.LOCAL_IMPLEMENTED_BOUNDED: 1,
            },
        )
        self.assertEqual(
            manifest["source_implementation_states"],
            {
                integration.BLUEPRINT_IMPORTED: 101,
                integration.SOURCE_NOT_APPLICABLE: 1,
            },
        )
        self.assertEqual(
            manifest["repository_handler_states"],
            {integration.LOCAL_IMPLEMENTED_BOUNDED: 102},
        )
        self.assertFalse(manifest["source_scripts_executed"])
        self.assertFalse(manifest["archive_content_executed"])
        self.assertEqual(manifest["runtime_evidence_status"], "NOT_RUN")
        self.assertEqual(manifest["external_evidence_status"], "NOT_RUN")
        self.assertEqual(manifest["certification_status"], "NOT_CERTIFIED")
        runtime_binding = manifest["runtime_binding"]
        self.assertEqual(runtime_binding["module"], "elmos_software_factory")
        self.assertEqual(runtime_binding["state"], "BOUND_NOT_EXECUTED")
        self.assertEqual(runtime_binding["bound_skill_count"], 102)
        self.assertTrue(runtime_binding["external_actions_require_adapters"])
        self.assertEqual(
            set(runtime_binding["artifact_digests"]), set(integration.RUNTIME_ARTIFACTS)
        )
        source_mapping = manifest["canonical_source_path_mapping"]
        self.assertEqual(len(source_mapping), 102)
        mapping_by_logical = {item["logical_path"]: item for item in source_mapping}
        self.assertEqual(
            mapping_by_logical["AGENTS.md"],
            {
                "logical_path": "AGENTS.md",
                "materialized_path": integration.NEUTRALIZED_SOURCE_PATHS["AGENTS.md"],
                "mode": "0644",
                "reason": "ARCHIVE_INSTRUCTION_FILENAME_NEUTRALIZED",
                "sha256": "sha256:" + snapshot.canonical_files["AGENTS.md"].sha256,
            },
        )
        self.assertEqual(
            sum(item["logical_path"].endswith("/SKILL.md") for item in source_mapping),
            101,
        )
        self.assertEqual(manifest["active_archive_instruction_filenames"], [])

        for record in manifest["skills"]:
            name = record["name"]
            source_name = record["source_name"]
            left = root / integration.INSTALL_ROOTS[0] / name
            right = root / integration.INSTALL_ROOTS[1] / name
            self.assertEqual(
                integration._read_tree(left), integration._read_tree(right)
            )
            installed_skill = (left / "SKILL.md").read_text(encoding="utf-8")
            right_installed_skill = (right / "SKILL.md").read_text(encoding="utf-8")
            interface = (left / "agents/openai.yaml").read_text(encoding="utf-8")
            contract = json.loads(
                (left / "compiled-contract.json").read_text(encoding="utf-8")
            )
            self.assertTrue(installed_skill.startswith(f'---\nname: "{name}"\n'))
            self.assertEqual(installed_skill, right_installed_skill)
            self.assertIn(f"${name}", interface)
            self.assertIn("## Repository Runtime", installed_skill)
            self.assertIn(f"--skill {source_name} --request <file>", installed_skill)
            contract_binding = contract["runtime_binding"]
            self.assertEqual(contract_binding["module"], "elmos_software_factory")
            self.assertEqual(contract_binding["skill_name"], source_name)
            self.assertEqual(contract_binding["state"], "BOUND_NOT_EXECUTED")
            self.assertIn(contract_binding["mode"], {"local", "requires_adapter"})
            self.assertEqual(
                contract_binding["runtime_artifact_set_sha256"],
                runtime_binding["runtime_artifact_set_sha256"],
            )
            self.assertEqual(contract["runtime_evidence_status"], "NOT_RUN")
            self.assertEqual(contract["external_evidence_status"], "NOT_RUN")
            self.assertEqual(contract["certification_status"], "NOT_CERTIFIED")
            self.assertFalse(contract["archive_content_executed"])
            if name == integration.ROOT_SKILL_NAME:
                self.assertEqual(
                    record["implementation_state"],
                    integration.LOCAL_IMPLEMENTED_BOUNDED,
                )
                self.assertEqual(
                    record["source_implementation_state"],
                    integration.SOURCE_NOT_APPLICABLE,
                )
                self.assertFalse(contract["source"]["archive_member"])
            else:
                self.assertEqual(contract["name"], name)
                self.assertEqual(contract["source"]["name"], source_name)
                self.assertEqual(record["installed_name"], name)
                self.assertEqual(
                    record["implementation_state"], integration.BLUEPRINT_IMPORTED
                )
                self.assertEqual(
                    record["source_implementation_state"],
                    integration.BLUEPRINT_IMPORTED,
                )
            self.assertEqual(
                record["repository_handler_state"],
                integration.LOCAL_IMPLEMENTED_BOUNDED,
            )
            self.assertEqual(
                contract["source_implementation_state"],
                record["source_implementation_state"],
            )
            self.assertEqual(
                contract["repository_handler_state"],
                integration.LOCAL_IMPLEMENTED_BOUNDED,
            )

        for operation in ("--install", "--check"):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = integration.main(
                    [
                        operation,
                        "--root",
                        str(root),
                        "--archives",
                        str(archive_directory),
                    ]
                )
            self.assertEqual(result, 0, output.getvalue())
            self.assertNotEqual(
                json.loads(output.getvalue())["decision"], "BLOCKED"
            )

    def test_drift_and_unowned_collision_are_refused(self) -> None:
        temporary, root, archive_directory = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        integration.install_integration(root, archive_directory)
        drifted = (
            root
            / integration.INSTALL_ROOTS[1]
            / integration.ROOT_SKILL_NAME
            / "SKILL.md"
        )
        drifted.write_bytes(drifted.read_bytes() + b"\nDRIFT\n")

        with self.assertRaisesRegex(integration.IntegrationError, "drifted"):
            integration.check_integration(root, archive_directory)
        with self.assertRaisesRegex(integration.IntegrationError, "refusing unowned"):
            integration.install_integration(root, archive_directory)

        second_temporary, second_root, second_archives = self.temporary_repository()
        self.addCleanup(second_temporary.cleanup)
        collision = (
            second_root
            / integration.INSTALL_ROOTS[0]
            / integration.ROOT_SKILL_NAME
        )
        collision.mkdir(parents=True)
        marker = collision / "user-owned.txt"
        marker.write_text("preserve me\n", encoding="utf-8")
        with self.assertRaisesRegex(integration.IntegrationError, "refusing unowned"):
            integration.install_integration(second_root, second_archives)
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve me\n")
        self.assertFalse((second_root / integration.SOURCE_RELATIVE).exists())

    def test_stale_namespace_wrapper_is_detected_without_deletion(self) -> None:
        temporary, root, archive_directory = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        stale = root / integration.INSTALL_ROOTS[1] / "elmos-stale-wrapper"
        stale.mkdir(parents=True)
        contract = stale / "compiled-contract.json"
        contract.write_text(
            json.dumps({"namespace": integration.NAMESPACE, "name": stale.name}) + "\n",
            encoding="utf-8",
        )
        marker = stale / "preserve-me.txt"
        marker.write_text("preserve me\n", encoding="utf-8")

        with self.assertRaisesRegex(integration.IntegrationError, "stale managed Skill wrapper"):
            integration.install_integration(root, archive_directory)
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve me\n")
        self.assertFalse((root / integration.SOURCE_RELATIVE).exists())
        contract.write_text(
            '{"namespace":"' + integration.NAMESPACE + '","broken":\n',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(integration.IntegrationError, "malformed stale Skill wrapper"):
            integration.install_integration(root, archive_directory)
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve me\n")

        second_temporary, second_root, second_archives = self.temporary_repository()
        self.addCleanup(second_temporary.cleanup)
        first_root_stale = (
            second_root / integration.INSTALL_ROOTS[0] / "elmos-stale-first-root"
        )
        first_root_stale.mkdir(parents=True)
        (first_root_stale / "compiled-contract.json").write_text(
            json.dumps({"namespace": integration.NAMESPACE}) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(integration.IntegrationError, "stale managed Skill wrapper"):
            integration.install_integration(second_root, second_archives)
        self.assertTrue(first_root_stale.is_dir())

    def test_owned_name_collisions_install_as_aliases_without_overwrite(self) -> None:
        temporary, root, archive_directory = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        preserved: dict[tuple[str, str], object] = {}
        for install_root in integration.INSTALL_ROOTS:
            for source_name in integration.INSTALLED_NAME_OVERRIDES:
                original = root / install_root / source_name
                (original / "agents").mkdir(parents=True)
                os.chmod(original, 0o755)
                os.chmod(original / "agents", 0o755)
                (original / "SKILL.md").write_text(
                    f"---\nname: {source_name}\ndescription: Project Intelligence owner\n---\n\nOwned.\n",
                    encoding="utf-8",
                )
                (original / "agents/openai.yaml").write_text(
                    "interface:\n  display_name: Project Intelligence\n",
                    encoding="utf-8",
                )
                (original / "compiled-contract.json").write_text(
                    json.dumps(
                        {
                            "namespace": "elmos-project-intelligence-v1.1",
                            "name": source_name,
                            "owner": "project-intelligence",
                        },
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                preserved[(install_root.as_posix(), source_name)] = integration._read_tree(
                    original
                )

        snapshot = integration.install_integration(root, archive_directory)
        integration.check_integration(root, archive_directory)
        integration.install_integration(root, archive_directory)
        for install_root in integration.INSTALL_ROOTS:
            for source_name, alias in integration.INSTALLED_NAME_OVERRIDES.items():
                original = root / install_root / source_name
                self.assertEqual(
                    integration._read_tree(original),
                    preserved[(install_root.as_posix(), source_name)],
                )
                alias_root = root / install_root / alias
                active = (alias_root / "SKILL.md").read_text(encoding="utf-8")
                interface = (alias_root / "agents/openai.yaml").read_text(
                    encoding="utf-8"
                )
                contract = json.loads(
                    (alias_root / "compiled-contract.json").read_text(encoding="utf-8")
                )
                self.assertTrue(active.startswith(f'---\nname: "{alias}"\n'))
                self.assertIn(f"${alias}", interface)
                self.assertIn(f"--skill {source_name} --request <file>", active)
                self.assertEqual(contract["name"], alias)
                self.assertEqual(contract["source"]["name"], source_name)
                self.assertEqual(contract["runtime_binding"]["skill_name"], source_name)
                self.assertEqual(
                    contract["installed_name_resolution"]["reason"],
                    integration.INSTALLED_NAME_OVERRIDE_REASON,
                )
        expected = integration.build_expected(snapshot, root)
        self.assertEqual(len(expected["skill_trees"]), 102)

    def test_managed_directories_are_0755_under_restrictive_umask(self) -> None:
        temporary, root, archive_directory = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        previous_umask = os.umask(0o077)
        try:
            snapshot = integration.install_integration(root, archive_directory)
        finally:
            os.umask(previous_umask)
        expected = integration.build_expected(snapshot, root)
        for action in integration._managed_actions(root, expected):
            directories = [action.destination]
            directories.extend(path for path in action.destination.rglob("*") if path.is_dir())
            for directory in directories:
                self.assertEqual(
                    stat.S_IMODE(directory.stat().st_mode),
                    integration.DIRECTORY_MODE,
                    str(directory),
                )
        for generated_parent in (
            root / ".agents",
            root / ".agents/skills",
            root / "agent-skills",
            root / "agent-skills/runtime",
        ):
            self.assertEqual(stat.S_IMODE(generated_parent.stat().st_mode), 0o755)
        nested = root / integration.INSTALL_ROOTS[0] / integration.ROOT_SKILL_NAME / "agents"
        os.chmod(nested, 0o700)
        with self.assertRaisesRegex(integration.IntegrationError, "directory mode drifted"):
            integration.check_integration(root, archive_directory)

    def test_internal_final_component_symlink_is_refused_without_touching_target(self) -> None:
        temporary, root, archive_directory = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        target = root / "user-owned-target"
        target.mkdir()
        marker = target / "preserve-me.txt"
        marker.write_text("preserve me\n", encoding="utf-8")
        managed = root / integration.SOURCE_RELATIVE
        managed.parent.mkdir(parents=True, exist_ok=True)
        managed.symlink_to(target, target_is_directory=True)

        with self.assertRaisesRegex(
            integration.IntegrationError, "managed destination is a symlink"
        ):
            integration.install_integration(root, archive_directory)

        self.assertTrue(managed.is_symlink())
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve me\n")
        self.assertEqual(sorted(path.name for path in target.iterdir()), [marker.name])


if __name__ == "__main__":
    unittest.main()
