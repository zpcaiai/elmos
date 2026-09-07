from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SkillPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.installer = load_module("elmos_installer", ROOT / "scripts" / "install_skillpack.py")
        cls.database_selector = load_module("elmos_database_selector", ROOT / "tools" / "database_selector.py")
        cls.architecture_selector = load_module("elmos_architecture_selector", ROOT / "tools" / "architecture_selector.py")
        cls.plan_estimator = load_module("elmos_plan_estimator", ROOT / "tools" / "plan_estimator.py")
        cls.registry = json.loads((ROOT / "catalog" / "database-capabilities.json").read_text(encoding="utf-8"))

    def quiet_run_installer(self, args: list[str]) -> int:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return self.installer.run(args)

    def test_01_skill_count_dependency_graph_and_full_profile(self) -> None:
        graph = self.installer.load_skill_graph()
        self.assertEqual(46, len(graph))
        full = self.installer.load_profile("full")
        expanded = self.installer.expand_dependencies(full["skills"], graph)
        self.assertEqual(set(graph), set(expanded))
        self.assertEqual(len(expanded), len(set(expanded)))

    def test_02_all_profiles_expand_to_known_skills(self) -> None:
        graph = self.installer.load_skill_graph()
        for path in sorted((ROOT / "profiles").glob("*.json")):
            profile = self.installer.load_profile(path.stem)
            expanded = self.installer.expand_dependencies(profile["skills"], graph)
            self.assertTrue(expanded)
            self.assertTrue(set(expanded) <= set(graph))

    def test_03_examples_validate_against_schemas(self) -> None:
        pairs = {
            "requirements.json": "workload-requirements.schema.json",
            "database-decision.json": "database-decision.schema.json",
            "architecture-decision.json": "architecture-pattern-decision.schema.json",
            "cost-and-eta.json": "cost-and-eta.schema.json",
        }
        for directory in sorted((ROOT / "examples").iterdir()):
            if not directory.is_dir():
                continue
            for data_name, schema_name in pairs.items():
                instance = json.loads((directory / data_name).read_text(encoding="utf-8"))
                schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
                errors = list(Draft202012Validator(schema).iter_errors(instance))
                self.assertFalse(errors, f"{directory.name}/{data_name}: {errors}")

    def test_04_database_selector_is_deterministic_and_role_based(self) -> None:
        for directory in sorted((ROOT / "examples").iterdir()):
            if not directory.is_dir():
                continue
            req = json.loads((directory / "requirements.json").read_text(encoding="utf-8"))
            expected = json.loads((directory / "database-decision.json").read_text(encoding="utf-8"))
            actual = self.database_selector.select(req, self.registry, 3)
            self.assertEqual(expected, actual)
            roles = {item["role"] for item in actual["roles"]}
            self.assertTrue(roles)
            for role in actual["roles"]:
                self.assertLessEqual(len(role["selected"]), 1)
                self.assertTrue(role["rationale"])

    def test_05_tenant_isolation_does_not_reject_non_record_roles(self) -> None:
        req = json.loads((ROOT / "examples" / "iot-realtime" / "requirements.json").read_text(encoding="utf-8"))
        actual = self.database_selector.select(req, self.registry, 3)
        by_role = {item["role"]: item for item in actual["roles"]}
        for role in ("event-backbone", "stream-processing", "lakehouse", "real-time-analytics"):
            self.assertIn(role, by_role)
            self.assertTrue(by_role[role]["selected"], f"{role} should retain a candidate")

    def test_06_architecture_selector_covers_batch_stream_lakehouse_and_fabric(self) -> None:
        offline = json.loads((ROOT / "examples" / "offline-lakehouse" / "requirements.json").read_text(encoding="utf-8"))
        offline_result = self.architecture_selector.choose(offline)
        self.assertEqual("batch-warehouse", offline_result["primary_pattern"])
        self.assertIn("lakehouse", offline_result["secondary_patterns"])
        self.assertIn("data-fabric-overlay", offline_result["overlays"])

        iot = json.loads((ROOT / "examples" / "iot-realtime" / "requirements.json").read_text(encoding="utf-8"))
        iot_result = self.architecture_selector.choose(iot)
        self.assertEqual("streaming-kappa", iot_result["primary_pattern"])
        self.assertIn("lakehouse", iot_result["secondary_patterns"])

    def test_07_estimator_keeps_machine_human_and_hitl_time_separate(self) -> None:
        req = json.loads((ROOT / "examples" / "realtime-user-profile" / "requirements.json").read_text(encoding="utf-8"))
        result = self.plan_estimator.estimate(req, None, None, "USD")
        self.assertEqual("hours", result["system_autonomous_runtime"]["unit"])
        self.assertEqual("person-hours", result["human_equivalent_effort"]["unit"])
        self.assertEqual("hours", result["human_in_the_loop_delay"]["unit"])
        self.assertGreater(result["human_equivalent_effort"]["likely"], result["system_autonomous_runtime"]["likely"])
        self.assertEqual("UNPRICED", result["estimated_token_cost"]["currency"])

    def test_08_installer_install_reinstall_and_receipt_scoped_uninstall(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-install-test-") as tmp:
            target = Path(tmp) / "skills"
            args = ["install", "--target", "custom", "--dest", str(target), "--profile", "database"]
            self.assertEqual(0, self.quiet_run_installer(args))
            receipt_path = target / self.installer.RECEIPT_NAME
            self.assertTrue(receipt_path.is_file())
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(13, len(receipt["skills"]))

            # Exact package-owned content is a safe no-op without --force.
            self.assertEqual(0, self.quiet_run_installer(args))

            unmanaged = target / "elmos-user-keep"
            unmanaged.mkdir()
            (unmanaged / "SKILL.md").write_text("unmanaged\n", encoding="utf-8")
            uninstall = ["uninstall", "--target", "custom", "--dest", str(target), "--profile", "database"]
            self.assertEqual(0, self.quiet_run_installer(uninstall))
            self.assertTrue(unmanaged.is_dir())
            self.assertFalse(receipt_path.exists())
            self.assertFalse(any((target / name).exists() for name in receipt["skills"]))

    def test_09_installer_conflict_fails_and_force_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-conflict-test-") as tmp:
            target = Path(tmp) / "skills"
            conflict = target / "elmos-data-requirement-intake"
            conflict.mkdir(parents=True)
            marker = conflict / "SKILL.md"
            marker.write_text("user-owned\n", encoding="utf-8")
            base_args = ["install", "--target", "custom", "--dest", str(target), "--profile", "database"]
            self.assertEqual(2, self.quiet_run_installer(base_args))
            self.assertEqual("user-owned\n", marker.read_text(encoding="utf-8"))
            self.assertEqual(0, self.quiet_run_installer(base_args + ["--force"]))
            self.assertIn("name: elmos-data-requirement-intake", marker.read_text(encoding="utf-8"))

            keep = target / "elmos-user-keep"
            keep.mkdir()
            (keep / "SKILL.md").write_text("keep\n", encoding="utf-8")
            uninstall = ["uninstall", "--target", "custom", "--dest", str(target), "--all"]
            self.assertEqual(0, self.quiet_run_installer(uninstall))
            self.assertTrue(keep.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
