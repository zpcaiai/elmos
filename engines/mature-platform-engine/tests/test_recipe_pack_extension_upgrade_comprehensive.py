"""Comprehensive test suite for RecipePackExtensionUpgradeEngine (B38 - Skill 1342)."""

import unittest

from elmos_mature_platform.recipe_pack_extension_upgrade_engine import (
    RecipePackExtensionUpgradeEngine,
)
from elmos_mature_platform.types import (
    ArtifactPackageType,
    PackageArtifact,
    PackageDependency,
    PackageUpgradePlan,
    PackageUpgradeStatus,
    PackageUpgradeStrategy,
)


class TestRecipePackExtensionUpgradeComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = RecipePackExtensionUpgradeEngine()

    def test_register_and_retrieve_package(self):
        pkg = PackageArtifact(
            package_id="pkg-spring-recipe",
            name="spring-modernization-recipe",
            version="2.1.0",
            package_type=ArtifactPackageType.RECIPE,
            sha256="",
            dependencies=[
                PackageDependency(name="core-framework-pack", version_constraint=">=1.5.0")
            ],
            supported_editions=["saas", "vpc", "sovereign"],
        )
        pid = self.engine.register_package(pkg)
        self.assertEqual(pid, "pkg-spring-recipe")

        retrieved = self.engine.get_package("pkg-spring-recipe")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "spring-modernization-recipe")
        self.assertTrue(retrieved.sha256)  # Checksum auto-generated

    def test_find_package_by_name_and_version(self):
        pkg = PackageArtifact(
            package_id="pkg-ext-sql",
            name="oracle-to-postgres-pack",
            version="3.0.0",
            package_type=ArtifactPackageType.PACK,
            sha256="abc123hash",
        )
        self.engine.register_package(pkg)
        found = self.engine.find_package("oracle-to-postgres-pack", "3.0.0")
        self.assertIsNotNone(found)
        self.assertEqual(found.package_id, "pkg-ext-sql")

        missing = self.engine.find_package("oracle-to-postgres-pack", "9.9.9")
        self.assertIsNone(missing)

    def test_dependency_resolution_satisfied(self):
        pkg = PackageArtifact(
            package_id="pkg-ext-kafka",
            name="kafka-stream-ext",
            version="1.2.0",
            package_type=ArtifactPackageType.EXTENSION,
            sha256="",
            dependencies=[
                PackageDependency(name="jvm-runtime", version_constraint=">=17.0.0"),
                PackageDependency(name="stream-core", version_constraint="==2.0.0"),
            ],
        )
        self.engine.register_package(pkg)

        installed = {"jvm-runtime": "21.0.1", "stream-core": "2.0.0"}
        res = self.engine.check_dependencies("pkg-ext-kafka", installed)
        self.assertTrue(res["compatible"])
        self.assertEqual(len(res["missing"]), 0)
        self.assertEqual(len(res["conflicts"]), 0)

    def test_dependency_resolution_missing_and_conflict(self):
        pkg = PackageArtifact(
            package_id="pkg-ext-test",
            name="test-ext",
            version="1.0.0",
            package_type=ArtifactPackageType.EXTENSION,
            sha256="",
            dependencies=[
                PackageDependency(name="dep-a", version_constraint=">=2.0.0", mandatory=True),
                PackageDependency(name="dep-b", version_constraint="==3.0.0", mandatory=True),
            ],
        )
        self.engine.register_package(pkg)

        # dep-a is version 1.0 (conflict), dep-b is missing
        installed = {"dep-a": "1.0.0"}
        res = self.engine.check_dependencies("pkg-ext-test", installed)
        self.assertFalse(res["compatible"])
        self.assertIn("dep-b", res["missing"])
        self.assertTrue(any("dep-a" in c for c in res["conflicts"]))

    def test_create_and_execute_upgrade_plan(self):
        plan = PackageUpgradePlan(
            plan_id="plan-roll-1",
            package_name="spring-recipe",
            package_type=ArtifactPackageType.RECIPE,
            from_version="1.0.0",
            to_version="2.0.0",
            strategy=PackageUpgradeStrategy.ROLLING,
            target_deployments=["dep-us-east-1", "dep-eu-west-1"],
            rollback_on_failure=True,
        )
        pid = self.engine.create_upgrade_plan(plan)
        self.assertEqual(pid, "plan-roll-1")

        # Step 1: East
        p1 = self.engine.execute_upgrade("plan-roll-1", "dep-us-east-1")
        self.assertEqual(p1.status, PackageUpgradeStatus.IN_PROGRESS)
        self.assertEqual(p1.applied_deployments, ["dep-us-east-1"])

        # Step 2: West -> Complete
        p2 = self.engine.execute_upgrade("plan-roll-1", "dep-eu-west-1")
        self.assertEqual(p2.status, PackageUpgradeStatus.APPLIED)
        self.assertTrue(p2.completed_at)

    def test_rollback_upgrade(self):
        plan = PackageUpgradePlan(
            plan_id="plan-roll-2",
            package_name="cobol-pack",
            package_type=ArtifactPackageType.PACK,
            from_version="4.0.0",
            to_version="5.0.0",
            target_deployments=["dep-1"],
        )
        self.engine.create_upgrade_plan(plan)
        self.engine.execute_upgrade("plan-roll-2", "dep-1")
        self.assertIn("dep-1", plan.applied_deployments)

        # Rollback
        rolled = self.engine.rollback_upgrade("plan-roll-2", "dep-1")
        self.assertEqual(rolled.status, PackageUpgradeStatus.ROLLED_BACK)
        self.assertNotIn("dep-1", rolled.applied_deployments)

    def test_fail_upgrade_auto_rollbacks_when_configured(self):
        plan = PackageUpgradePlan(
            plan_id="plan-auto-rb",
            package_name="payment-ext",
            package_type=ArtifactPackageType.EXTENSION,
            from_version="1.1.0",
            to_version="1.2.0",
            target_deployments=["dep-prod-1", "dep-prod-2"],
            rollback_on_failure=True,
        )
        self.engine.create_upgrade_plan(plan)
        self.engine.execute_upgrade("plan-auto-rb", "dep-prod-1")

        failed = self.engine.fail_upgrade("plan-auto-rb", "Healthcheck timed out")
        self.assertEqual(failed.status, PackageUpgradeStatus.ROLLED_BACK)
        self.assertEqual(len(failed.applied_deployments), 0)
        self.assertEqual(failed.error_message, "Healthcheck timed out")

    def test_get_upgrade_summary(self):
        pkg = PackageArtifact("p1", "rec-1", "1.0", ArtifactPackageType.RECIPE, "hash")
        self.engine.register_package(pkg)
        plan = PackageUpgradePlan("pl1", "rec-1", ArtifactPackageType.RECIPE, "1.0", "2.0")
        self.engine.create_upgrade_plan(plan)

        summary = self.engine.get_upgrade_summary()
        self.assertEqual(summary["total_packages_registered"], 1)
        self.assertEqual(summary["total_plans"], 1)
        self.assertIn("pending", summary["plans_by_status"])


if __name__ == "__main__":
    unittest.main()
