from __future__ import annotations

import hashlib
import json
import shutil
import stat
import sys
import tempfile
import unittest
import warnings
import zipfile
from collections import Counter
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLING_ROOT = REPOSITORY_ROOT / "tooling"
if str(TOOLING_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLING_ROOT))

import import_build_cache_parity_skills as integration  # noqa: E402


class BuildCacheParitySkillImportTest(unittest.TestCase):
    def temporary_repository(self, *, populate_runtime: bool = False) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory(prefix="build-cache-parity-import-")
        root = Path(temporary.name)
        archive = root / integration.ARCHIVE_RELATIVE
        archive.parent.mkdir(parents=True)
        shutil.copy2(REPOSITORY_ROOT / integration.ARCHIVE_RELATIVE, archive)
        v11 = root / integration.V11_SOURCE_RELATIVE
        v11.parent.mkdir(parents=True)
        shutil.copytree(REPOSITORY_ROOT / integration.V11_SOURCE_RELATIVE, v11, copy_function=shutil.copy2)
        integration.extract_source(root)
        if populate_runtime:
            for name in integration.V11_SKILLS:
                source = v11 / "agent-skills/runtime" / name / "SKILL.md"
                destination = root / integration.INSTALL_ROOTS[0] / name / "SKILL.md"
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        return temporary, root

    def write_archive(self, path: Path, entries: list[tuple[str, bytes, int]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as handle:
            for name, content, mode in entries:
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = mode << 16
                handle.writestr(info, content)

    def tree_digest(self, path: Path) -> str:
        digest = hashlib.sha256()
        for entry in sorted(item for item in path.rglob("*") if item.is_file()):
            digest.update(entry.relative_to(path).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(entry.read_bytes())
        return digest.hexdigest()

    def test_archive_has_exact_pinned_inventory_checksums_and_dag(self) -> None:
        summary = integration.inspect_archive(REPOSITORY_ROOT / integration.ARCHIVE_RELATIVE)

        self.assertEqual(len(summary.files), 146)
        self.assertEqual(len(summary.directories), 63)
        self.assertEqual(tuple(summary.manifest["topological_order"]), integration.EXPECTED_SKILLS)
        self.assertEqual(sum(len(value) for value in summary.dependencies.values()), 133)
        self.assertEqual(summary.manifest["claim_policy"]["mode"], "measured_only")
        self.assertEqual(
            Counter(payload.mode for payload in summary.files.values()),
            Counter(integration.EXPECTED_ARCHIVE_MODE_COUNTS),
        )

    def test_v11_lineage_is_frontmatter_only_for_all_completed_skills(self) -> None:
        summary = integration.inspect_archive(REPOSITORY_ROOT / integration.ARCHIVE_RELATIVE)
        v11 = integration._load_v11_skills(REPOSITORY_ROOT)

        self.assertEqual(tuple(v11), integration.V11_SKILLS)
        for name in integration.V11_SKILLS:
            integration._assert_frontmatter_only_upgrade(
                name,
                v11[name],
                summary.files[f"agent-skills/runtime/{name}/SKILL.md"].content,
            )

    def test_safe_extract_is_exact_idempotent_and_normalizes_directory_modes(self) -> None:
        temporary, root = self.temporary_repository()
        self.addCleanup(temporary.cleanup)
        source = root / integration.SOURCE_RELATIVE

        first = integration.extract_source(root)
        second = integration.extract_source(root)

        self.assertEqual(first.files, second.files)
        self.assertEqual(stat.S_IMODE((source / "validate.sh").stat().st_mode), 0o755)
        self.assertEqual(
            stat.S_IMODE(
                (source / "agent-skills/runtime/elmos-cache-system-architecture/SKILL.md").stat().st_mode
            ),
            0o644,
        )
        self.assertEqual(stat.S_IMODE((source / "agent-skills/runtime").stat().st_mode), 0o755)

    def test_archive_tamper_fails_before_extraction(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="build-cache-parity-tamper-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        archive = root / integration.ARCHIVE_RELATIVE
        archive.parent.mkdir(parents=True)
        shutil.copy2(REPOSITORY_ROOT / integration.ARCHIVE_RELATIVE, archive)
        with archive.open("ab") as handle:
            handle.write(b"tamper")

        with self.assertRaisesRegex(integration.IntegrationError, "trusted SHA-256 mismatch"):
            integration.extract_source(root)
        self.assertFalse((root / integration.SOURCE_RELATIVE).exists())

    def test_archive_path_traversal_and_symlinks_are_rejected(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="build-cache-parity-unsafe-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        traversal = root / "traversal.zip"
        archive_root = integration.ARCHIVE_DIRECTORY
        self.write_archive(
            traversal,
            [
                (f"{archive_root}/", b"", stat.S_IFDIR | 0o755),
                (f"{archive_root}/../escape", b"escape", stat.S_IFREG | 0o644),
            ],
        )
        with self.assertRaisesRegex(integration.IntegrationError, "escapes|normalized"):
            integration.inspect_archive(traversal, trusted_sha256=None, enforce_pinned_shape=False)

        symlink = root / "symlink.zip"
        self.write_archive(
            symlink,
            [
                (f"{archive_root}/", b"", stat.S_IFDIR | 0o755),
                (f"{archive_root}/link", b"../../escape", stat.S_IFLNK | 0o777),
            ],
        )
        with self.assertRaisesRegex(integration.IntegrationError, "unsafe archive file type"):
            integration.inspect_archive(symlink, trusted_sha256=None, enforce_pinned_shape=False)

    def test_duplicate_archive_entry_is_rejected(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="build-cache-parity-duplicate-")
        self.addCleanup(temporary.cleanup)
        archive = Path(temporary.name) / "duplicate.zip"
        archive_root = integration.ARCHIVE_DIRECTORY
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            self.write_archive(
                archive,
                [
                    (f"{archive_root}/", b"", stat.S_IFDIR | 0o755),
                    (f"{archive_root}/same", b"one", stat.S_IFREG | 0o644),
                    (f"{archive_root}/same", b"two", stat.S_IFREG | 0o644),
                ],
            )
        with self.assertRaisesRegex(integration.IntegrationError, "duplicate archive entry"):
            integration.inspect_archive(archive, trusted_sha256=None, enforce_pinned_shape=False)

    def test_install_upgrades_only_exact_v11_and_creates_exact_four_roots(self) -> None:
        temporary, root = self.temporary_repository(populate_runtime=True)
        self.addCleanup(temporary.cleanup)
        v11 = root / integration.V11_SOURCE_RELATIVE
        v11_before = self.tree_digest(v11)
        unrelated = root / ".agents/skills/unrelated-user-skill/KEEP"
        unrelated.parent.mkdir(parents=True)
        unrelated.write_text("preserve\n", encoding="utf-8")
        sibling_doc = root / integration.DOC_RELATIVE / "RUNBOOK.md"
        sibling_doc.parent.mkdir(parents=True)
        sibling_doc.write_text("operator-owned sibling\n", encoding="utf-8")
        restrictive_v11 = root / integration.INSTALL_ROOTS[0] / integration.V11_SKILLS[0] / "SKILL.md"
        restrictive_v11.chmod(0o600)

        _summary, actions = integration.install(root)

        self.assertEqual(Counter(action.operation for action in actions), {"create": 138, "upgrade": 31})
        self.assertEqual(self.tree_digest(v11), v11_before)
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "preserve\n")
        self.assertEqual(sibling_doc.read_text(encoding="utf-8"), "operator-owned sibling\n")
        for name in integration.EXPECTED_SKILLS:
            trees = [integration._read_tree(root / install_root / name) for install_root in integration.INSTALL_ROOTS]
            self.assertTrue(all(tree == trees[0] for tree in trees[1:]))
            installed = trees[0]["SKILL.md"].content.decode("utf-8")
            self.assertIn("version: 1.2.0", installed)
            self.assertIn("package: elmos-build-cache-staging-codex-claude-parity", installed)
            self.assertEqual(trees[0]["SKILL.md"].mode, 0o644)

        manifest = json.loads(
            (root / integration.DOC_RELATIVE / "installed-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["skill_count"], 42)
        self.assertEqual(manifest["retained_v1_1_skill_count"], 31)
        self.assertEqual(manifest["new_v1_2_skill_count"], 11)
        self.assertTrue(manifest["four_root_byte_identical"])
        self.assertFalse(manifest["package_scripts_executed"])
        self.assertEqual(manifest["external_evidence_status"], "NOT_RUN")
        self.assertEqual(manifest["certification"], "NOT_CERTIFIED")

        _summary, second_actions = integration.install(root)
        self.assertEqual(second_actions, [])
        integration.check_install(root)
        self.assertEqual(sibling_doc.read_text(encoding="utf-8"), "operator-owned sibling\n")

    def test_drifted_v11_collision_blocks_before_any_root_is_written(self) -> None:
        temporary, root = self.temporary_repository(populate_runtime=True)
        self.addCleanup(temporary.cleanup)
        drifted = root / integration.INSTALL_ROOTS[0] / integration.V11_SKILLS[0] / "SKILL.md"
        drifted.write_bytes(drifted.read_bytes() + b"\ndrift\n")

        with self.assertRaisesRegex(integration.IntegrationError, "drifted collision"):
            integration.install(root)

        self.assertFalse((root / ".agents/skills").exists())
        untouched = root / integration.INSTALL_ROOTS[0] / integration.V11_SKILLS[1] / "SKILL.md"
        self.assertIn("version: 1.1.0", untouched.read_text(encoding="utf-8"))

    def test_new_skill_collision_blocks_before_v11_upgrade(self) -> None:
        temporary, root = self.temporary_repository(populate_runtime=True)
        self.addCleanup(temporary.cleanup)
        collision = root / integration.INSTALL_ROOTS[0] / integration.NEW_V12_SKILLS[0] / "SKILL.md"
        collision.parent.mkdir(parents=True)
        collision.write_text("alien\n", encoding="utf-8")

        with self.assertRaisesRegex(integration.IntegrationError, "drifted collision"):
            integration.install(root)

        baseline = root / integration.INSTALL_ROOTS[0] / integration.V11_SKILLS[0] / "SKILL.md"
        self.assertIn("version: 1.1.0", baseline.read_text(encoding="utf-8"))

    def test_source_and_installed_mode_or_content_drift_fail_closed(self) -> None:
        temporary, root = self.temporary_repository(populate_runtime=True)
        self.addCleanup(temporary.cleanup)
        source_skill = root / integration.SOURCE_RELATIVE / "agent-skills/runtime" / integration.EXPECTED_SKILLS[0] / "SKILL.md"
        source_skill.write_bytes(source_skill.read_bytes() + b"tamper")
        with self.assertRaisesRegex(integration.IntegrationError, "immutable extracted source differs"):
            integration.extract_source(root)

        source_skill.write_bytes(
            (REPOSITORY_ROOT / integration.SOURCE_RELATIVE / "agent-skills/runtime" / integration.EXPECTED_SKILLS[0] / "SKILL.md").read_bytes()
        )
        integration.install(root)
        installed = root / ".claude/skills" / integration.EXPECTED_SKILLS[0] / "SKILL.md"
        installed.chmod(0o755)
        with self.assertRaisesRegex(integration.IntegrationError, "incomplete or drifted"):
            integration.check_install(root)


if __name__ == "__main__":
    unittest.main()
