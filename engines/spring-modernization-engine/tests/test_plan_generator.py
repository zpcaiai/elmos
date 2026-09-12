from elmos_spring_modernization.plan_generator import MigrationPlanGenerator
from elmos_spring_modernization.project_scanner import SpringProjectScanner
from elmos_spring_modernization.models import SpringVersion

def test_generate_plan():
    generator = MigrationPlanGenerator()
    scanner = SpringProjectScanner()
    profile = scanner.scan("/tmp")
    plan = generator.generate_plan(profile, SpringVersion.BOOT_3_2)
    assert plan.target_version == SpringVersion.BOOT_3_2
