from elmos_spring_modernization.plan_generator import MigrationPlanGenerator
from elmos_spring_modernization.models import SpringProjectProfile, SpringVersion, RiskLevel

def test_generate_plan():
    generator = MigrationPlanGenerator()
    profile = SpringProjectProfile(
        version=SpringVersion.BOOT_2_7,
        modules=["core", "web"],
        dependencies={
            "spring-boot-starter-web": "2.7.18",
            "spring-boot-starter-data-jpa": "2.7.18",
            "spring-boot-starter-security": "2.7.18"
        },
        config_format="yaml",
        security_mode="WebSecurityConfigurerAdapter",
        data_access_type="JPA"
    )
    plan = generator.generate_plan(profile, SpringVersion.BOOT_3_2)
    assert plan.target_version == SpringVersion.BOOT_3_2
    assert plan.source_version == SpringVersion.BOOT_2_7

    rule_ids = [r.rule_id for r in plan.rules]
    assert "RULE_JAKARTA_PERSISTENCE" in rule_ids
    assert "RULE_SECURITY_MATCHER" in rule_ids
    assert "RULE_JPA_GET_ONE_TO_REFERENCE" in rule_ids

    # Verify risk summary has counts
    assert plan.risk_summary[RiskLevel.MEDIUM] >= 1
    assert plan.risk_summary[RiskLevel.LOW] >= 1
    assert plan.estimated_changes > 0

    # Verify effort estimation
    effort = generator.estimate_effort(plan)
    assert effort > 0.0

    # Verify topological ordering
    order = generator.suggest_migration_order(plan)
    assert order[0].rule_id in ("RULE_POM_BOOT_PARENT_34", "RULE_JAVA_VERSION_17", "RULE_JAKARTA_PERSISTENCE")

    # Verify waves
    waves = generator.generate_migration_waves(plan, wave_size=2)
    assert len(waves) >= 2
    assert len(waves[0]) <= 2

def test_blocking_issues_detection():
    generator = MigrationPlanGenerator()
    profile = SpringProjectProfile(
        version=SpringVersion.BOOT_2_7,
        modules=["core"],
        dependencies={
            "spring-cloud-starter-netflix-zuul": "2.2.10.RELEASE",
            "springfox-swagger2": "2.9.2"
        },
        config_format="properties",
        security_mode="WebSecurityConfigurerAdapter",
        data_access_type="JPA"
    )
    plan = generator.generate_plan(profile, SpringVersion.BOOT_3_2)
    blockers = generator.identify_blocking_issues(plan, profile)
    assert len(blockers) >= 2
    assert any("netflix-zuul" in b.lower() for b in blockers)
    assert any("springfox" in b.lower() for b in blockers)
