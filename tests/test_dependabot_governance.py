from __future__ import annotations

import importlib.util
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "dependabot_governance.py"
SPEC = importlib.util.spec_from_file_location("dependabot_governance", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def alert(number: int, package: str, manifest_path: str) -> dict:
    return {
        "number": number,
        "dependency": {
            "package": {"ecosystem": "npm", "name": package},
            "manifest_path": manifest_path,
            "scope": "development",
            "relationship": "direct",
        },
        "security_advisory": {
            "ghsa_id": f"GHSA-test-{number}",
            "severity": "high",
        },
        "security_vulnerability": {
            "vulnerable_version_range": "< 2.0.0",
            "first_patched_version": {"identifier": "2.0.0"},
        },
    }


class DependabotGovernanceTest(unittest.TestCase):
    def test_registry_is_exact_alert_and_manifest_digest_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = (
                "client-packs/frontend-to-miniapp-vue3-wechat-v1/"
                "source-snapshots/example/package.json"
            )
            path = root / manifest
            path.parent.mkdir(parents=True)
            path.write_text(
                '{"devDependencies":{"vite":"1.0.0"}}\n', encoding="utf-8"
            )
            alerts = [alert(225, "vite", manifest)]
            now = datetime(2026, 9, 8, tzinfo=timezone.utc)

            registry = MODULE.build_registry(
                "zpcaiai/elmos", alerts, now=now, repo_root=root
            )

            self.assertEqual("2.0", registry["schema_version"])
            self.assertEqual([], registry["fixed_claims"])
            self.assertEqual("NOT_CERTIFIED", registry["certification"])
            exception = registry["exceptions"][0]
            self.assertEqual("immutable_source", exception["classification"])
            self.assertEqual("not_affected", exception["vex_status"])
            self.assertEqual(manifest, exception["manifest"]["path"])
            self.assertTrue(exception["manifest"]["sha256"].startswith("sha256:"))
            self.assertLessEqual(len(MODULE.dismissal_comment(exception)), 280)
            MODULE.validate_registry(registry, alerts, now=now, repo_root=root)
            vex = MODULE.build_vex_record(registry)
            self.assertEqual("review", vex["status"])
            self.assertEqual(
                "LOCAL_EXECUTED_SELF_ATTESTED", vex["metadata"]["evidenceStatus"]
            )
            self.assertEqual("NOT_AFFECTED", vex["records"][0]["analysis"]["state"])
            self.assertEqual([], vex["metadata"]["fixedClaims"])
            self.assertEqual("PREPARED", vex["metadata"]["githubDisposition"])
            self.assertEqual(0, vex["metadata"]["dismissedCount"])
            self.assertEqual("NOT_CERTIFIED", vex["metadata"]["certification"])

            path.write_text(
                '{"devDependencies":{"vite":"2.0.0"}}\n', encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "manifest identity changed"):
                MODULE.validate_registry(registry, alerts, now=now, repo_root=root)

    def test_vue2_compatibility_is_classified_before_broad_fixture_rule(self) -> None:
        manifest = (
            "client-packs/frontend-72-route-equivalence-v1/formal-campaign/"
            "engine/profiles/vue2/project/package.json"
        )
        self.assertEqual(
            "eol_compatibility", MODULE.classify(alert(91, "vue", manifest))
        )

    def test_route_formal_artifact_uses_narrow_certification_classification(self) -> None:
        manifest = (
            "routes/java-to-php/certification/formal-artifacts/engine-sources/"
            "runtime/typescript/sha256-example/package.json"
        )
        self.assertEqual(
            "immutable_certification_artifact",
            MODULE.classify(alert(330, "fast-xml-parser", manifest)),
        )

    def test_runtime_manifest_is_never_eligible(self) -> None:
        value = alert(999, "vite", "apps/web-console/package.json")
        self.assertIsNone(MODULE.classify(value))

    def test_alert_snapshot_digest_is_order_independent(self) -> None:
        first = alert(1, "vite", "client-packs/a/package.json")
        second = alert(2, "vue", "client-packs/b/package.json")
        self.assertEqual(
            MODULE.alert_snapshot_digest([first, second]),
            MODULE.alert_snapshot_digest([second, first]),
        )

    def test_missing_immutable_manifest_fails_closed(self) -> None:
        value = alert(
            223,
            "vitest",
            "skills/elmos-autonomous-qa-self-healing-skills-v1.1.0/"
            "examples/project-output-example/project/package.json",
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "manifest is unavailable"):
                MODULE.build_registry(
                    "zpcaiai/elmos", [value], repo_root=Path(directory)
                )

    def test_apply_resume_skips_an_already_closed_alert(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = (
                "client-packs/frontend-to-miniapp-vue3-wechat-v1/"
                "source-snapshots/example/package.json"
            )
            path = root / manifest
            path.parent.mkdir(parents=True)
            path.write_text("{}\n", encoding="utf-8")
            value = alert(225, "vite", manifest)
            registry = MODULE.build_registry(
                "zpcaiai/elmos",
                [value],
                now=datetime(2026, 9, 8, tzinfo=timezone.utc),
                repo_root=root,
            )
            value["state"] = "dismissed"
            with mock.patch.object(MODULE.subprocess, "run") as run:
                self.assertEqual(
                    0,
                    MODULE.dismiss_eligible(
                        "zpcaiai/elmos", registry, [value], repo_root=root
                    ),
                )
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
