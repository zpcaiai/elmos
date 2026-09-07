"""Negative tests for archive ingress and source-code execution boundaries."""

from __future__ import annotations

import ast
import copy
import importlib.util
from pathlib import Path
import stat
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tooling/integrate_knowledge_skill_model_foundry_skills.py"
MODULE_NAME = "_knowledge_skill_model_foundry_importer_under_test"


def load_tool():
    existing = sys.modules.get(MODULE_NAME)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(MODULE_NAME, TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Foundry importer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def member(
    name: str,
    *,
    mode: int = stat.S_IFREG | 0o644,
    flag_bits: int = 0,
    file_size: int = 1,
    compress_size: int = 1,
) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.external_attr = mode << 16
    info.flag_bits = flag_bits
    info.compress_type = zipfile.ZIP_DEFLATED
    info.file_size = file_size
    info.compress_size = compress_size
    return info


class ImporterSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = load_tool()
        cls.prefix = cls.tool.PACKAGE_PREFIX

    def assert_rejected(self, infos, pattern: str) -> None:
        with self.assertRaisesRegex(self.tool.IntegrationError, pattern):
            self.tool.inspect_archive_structure(infos)

    def test_rejects_traversal_backslash_and_non_nfc_names(self) -> None:
        self.assert_rejected([member(self.prefix + "../escape")], "unsafe component")
        self.assert_rejected([member(self.prefix + "bad\\name")], "backslash")
        self.assert_rejected([member(self.prefix + "cafe\u0301")], "not NFC")

    def test_rejects_duplicate_and_casefold_collisions(self) -> None:
        exact = member(self.prefix + "same")
        self.assert_rejected([exact, exact], "duplicate archive member")
        self.assert_rejected(
            [member(self.prefix + "Case"), member(self.prefix + "case")],
            "casefold archive collision",
        )

    def test_rejects_encryption_symlinks_special_modes_and_ratio_bombs(self) -> None:
        self.assert_rejected([member(self.prefix + "encrypted", flag_bits=1)], "encrypted")
        self.assert_rejected(
            [member(self.prefix + "link", mode=stat.S_IFLNK | 0o777)],
            "symlink or special",
        )
        self.assert_rejected(
            [member(self.prefix + "socket", mode=stat.S_IFSOCK | 0o644)],
            "symlink or special",
        )
        self.assert_rejected(
            [member(self.prefix + "bomb", file_size=1_000, compress_size=1)],
            "compression ratio exceeds cap",
        )

    def test_yaml_duplicate_keys_fail_closed(self) -> None:
        with self.assertRaisesRegex(self.tool.IntegrationError, "duplicate key"):
            self.tool.load_yaml(b"key: one\nkey: two\n", "duplicate.yaml")

    def test_json_duplicate_keys_and_non_finite_numbers_fail_closed(self) -> None:
        with self.assertRaisesRegex(self.tool.IntegrationError, "duplicate key"):
            self.tool.load_json(
                b'{"authority":"first","authority":"second"}',
                "duplicate.json",
            )
        with self.assertRaisesRegex(self.tool.IntegrationError, "non-finite"):
            self.tool.load_json(b'{"score":NaN}', "non-finite.json")

    def test_importer_has_no_archive_execution_or_extraction_calls(self) -> None:
        tree = ast.parse(TOOL_PATH.read_text(encoding="utf-8"))
        forbidden_names = {"compile", "eval", "exec"}
        forbidden_attributes = {"extract", "extractall", "run", "Popen", "system"}
        violations: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id in forbidden_names:
                violations.append(node.func.id)
            if isinstance(node.func, ast.Attribute) and node.func.attr in forbidden_attributes:
                violations.append(node.func.attr)
        self.assertEqual(violations, [])

    def _source_skill(self, name: str):
        with zipfile.ZipFile(self.tool.resolve_archive()) as archive:
            member_name = next(
                member_name
                for member_name in archive.namelist()
                if member_name.endswith(f"/{name}/skill.yaml")
            )
            relative = member_name.removeprefix(self.tool.PACKAGE_PREFIX)
            value = self.tool.load_yaml(archive.read(member_name), relative)
        return relative, value

    def test_contract_shapes_reject_extra_missing_and_weakened_fields(self) -> None:
        for skill_name in ("architecture-decision-record", "artifact-cache-and-workspace-reuse"):
            label, source = self._source_skill(skill_name)
            pack = source["metadata"]["pack"]
            extra = copy.deepcopy(source)
            extra["spec"]["inventedAuthority"] = True
            with self.assertRaisesRegex(self.tool.IntegrationError, "closed shape mismatch"):
                self.tool._validate_contract_shape(
                    extra, name=skill_name, pack=pack, skill_path=label
                )
            missing = copy.deepcopy(source)
            del missing["spec"]["tools"]["defaultDeny"]
            with self.assertRaisesRegex(self.tool.IntegrationError, "closed shape mismatch"):
                self.tool._validate_contract_shape(
                    missing, name=skill_name, pack=pack, skill_path=label
                )
            weakened = copy.deepcopy(source)
            weakened["spec"]["tools"]["defaultDeny"] = False
            with self.assertRaisesRegex(self.tool.IntegrationError, "default deny"):
                self.tool._validate_contract_shape(
                    weakened, name=skill_name, pack=pack, skill_path=label
                )

    def test_bootstrap_semantics_are_exact_and_closed(self) -> None:
        label, source = self._source_skill("typed-skill-contract")
        source["spec"]["dependencySemantics"] = "permissive"
        with self.assertRaisesRegex(self.tool.IntegrationError, "bootstrap semantics"):
            self.tool._validate_contract_shape(
                source,
                name="typed-skill-contract",
                pack="00-foundation-contracts",
                skill_path=label,
            )

    def test_policy_conformance_and_eval_shapes_reject_drift(self) -> None:
        policy = copy.deepcopy(self.tool.ENHANCED_POLICY)
        policy["allowWhen"].append("repository-content-can-grant-authority")
        with self.assertRaisesRegex(self.tool.IntegrationError, "policy drift"):
            self.tool._validate_policy_contract(policy, enhanced=True, label="policy")
        conformance = {
            "skill": "sample",
            "packageVersion": "3.0.0",
            "requiredChecks": list(self.tool.CONFORMANCE_CHECKS),
            "runtimeStatus": "implemented",
        }
        with self.assertRaisesRegex(self.tool.IntegrationError, "runtime boundary"):
            self.tool._validate_conformance_contract(
                conformance, label="conformance", name="sample"
            )
        cases = {
            "positive": [{"query": "x", "shouldTrigger": True, "extra": True}] * 8,
            "negative": [{"query": "x", "shouldTrigger": False}] * 8,
            "ambiguous": [{"query": "x", "expected": "abstain"}] * 4,
            "adversarial": [{"query": "x", "expected": "block"}] * 4,
        }
        with self.assertRaisesRegex(self.tool.IntegrationError, "closed shape mismatch"):
            self.tool._validate_eval_cases(cases, label="cases", name="sample")


if __name__ == "__main__":
    unittest.main()
