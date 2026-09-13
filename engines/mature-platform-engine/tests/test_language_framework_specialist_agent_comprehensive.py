"""Comprehensive test suite for LanguageFrameworkSpecialistAgentEngine (Batch 42 - Skill 1417)."""

import unittest

from elmos_mature_platform.language_framework_specialist_agent_engine import (
    LanguageFrameworkSpecialistAgentEngine,
)
from elmos_mature_platform.types import (
    SpecialistCapabilityRating,
    SpecialistDomain,
    SpecialistAgentProfile,
)


class TestLanguageFrameworkSpecialistAgentComprehensive(unittest.TestCase):
    """Rigorous tests covering specialist persona registration, capability matching, load balancing, and telemetry."""

    def setUp(self) -> None:
        self.engine = LanguageFrameworkSpecialistAgentEngine()

    def test_register_specialist_success(self) -> None:
        profile = SpecialistAgentProfile(
            specialist_id="",
            name="Spring Boot Senior Architect",
            domain=SpecialistDomain.JAVA_SPRING,
            rating=SpecialistCapabilityRating.MASTER,
            supported_frameworks=["spring-boot", "spring-cloud", "hibernate"],
            prompt_specialization="Focus on reactive Spring WebFlux and JDK 21 virtual threads",
        )
        spec_id = self.engine.register_specialist(profile)
        self.assertTrue(spec_id.startswith("spec-"))

        retrieved = self.engine.get_specialist(spec_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.domain, SpecialistDomain.JAVA_SPRING)
        self.assertEqual(retrieved.rating, SpecialistCapabilityRating.MASTER)

    def test_register_specialist_missing_name(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.register_specialist(
                SpecialistAgentProfile(
                    specialist_id="",
                    name="",
                    domain=SpecialistDomain.DOTNET_CSHARP,
                )
            )

    def test_dispatch_task_highest_rating_and_framework_matching(self) -> None:
        # Register 2 Java specialists: one novice, one expert with spring-boot
        self.engine.register_specialist(
            SpecialistAgentProfile(
                specialist_id="spec-novice",
                name="Java Junior",
                domain=SpecialistDomain.JAVA_SPRING,
                rating=SpecialistCapabilityRating.NOVICE,
                supported_frameworks=["spring-boot"],
            )
        )
        self.engine.register_specialist(
            SpecialistAgentProfile(
                specialist_id="spec-expert",
                name="Java Expert",
                domain=SpecialistDomain.JAVA_SPRING,
                rating=SpecialistCapabilityRating.EXPERT,
                supported_frameworks=["spring-boot", "spring-security"],
            )
        )

        decision = self.engine.dispatch_task(
            task_id="task-auth-migration",
            domain=SpecialistDomain.JAVA_SPRING,
            required_frameworks=["spring-security"],
        )
        self.assertEqual(decision.selected_specialist_id, "spec-expert")
        self.assertTrue(decision.match_score > 0)

        expert = self.engine.get_specialist("spec-expert")
        self.assertEqual(expert.active_tasks_count, 1)

    def test_dispatch_task_no_eligible_specialist(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.dispatch_task(
                task_id="task-cobol-01",
                domain=SpecialistDomain.LEGACY_COBOL,
            )

    def test_record_task_completion_and_success_rate(self) -> None:
        self.engine.register_specialist(
            SpecialistAgentProfile(
                specialist_id="spec-fastapi",
                name="FastAPI Pro",
                domain=SpecialistDomain.PYTHON_FASTAPI,
                rating=SpecialistCapabilityRating.EXPERT,
            )
        )
        self.engine.dispatch_task("task-py-1", SpecialistDomain.PYTHON_FASTAPI)
        spec = self.engine.get_specialist("spec-fastapi")
        self.assertEqual(spec.active_tasks_count, 1)

        # Complete task successfully
        self.engine.record_task_completion("spec-fastapi", success=True)
        self.assertEqual(spec.active_tasks_count, 0)
        self.assertEqual(spec.total_tasks_completed, 1)
        self.assertEqual(spec.success_rate_pct, 100.0)

        # Fail second task
        self.engine.record_task_completion("spec-fastapi", success=False)
        self.assertEqual(spec.total_tasks_completed, 2)
        self.assertEqual(spec.success_rate_pct, 50.0)

    def test_fleet_report(self) -> None:
        self.engine.register_specialist(
            SpecialistAgentProfile(
                specialist_id="s1", name="n1", domain=SpecialistDomain.RUST_SYSTEMS
            )
        )
        self.engine.register_specialist(
            SpecialistAgentProfile(
                specialist_id="s2", name="n2", domain=SpecialistDomain.GO_CLOUD
            )
        )
        report = self.engine.get_specialist_fleet_report()
        self.assertEqual(report["total_specialists"], 2)
        self.assertIn("rust_systems", report["by_domain"])
        self.assertIn("go_cloud", report["by_domain"])


if __name__ == "__main__":
    unittest.main()
