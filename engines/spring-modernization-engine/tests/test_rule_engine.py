from __future__ import annotations
from elmos_spring_modernization.rule_engine import RuleEngine
from elmos_spring_modernization.migration_rules import RULE_CATALOG
from elmos_spring_modernization.models import (
    MigrationPlan, SpringVersion, RiskLevel
)

def test_apply_rule():
    engine = RuleEngine()
    rule = RULE_CATALOG["RULE_001"]
    content, changes = engine.apply_rule("import javax.persistence.Entity1;", rule)
    assert "jakarta.persistence.Entity1" in content
    assert changes == 1

def test_apply_rules_to_file(tmp_path):
    engine = RuleEngine()
    file_path = tmp_path / "UserController.java"
    initial_code = (
        "package com.example;\n"
        "import javax.persistence.Entity1;\n"
        "import javax.servlet.http.HttpServletRequest;\n"
    )
    file_path.write_text(initial_code, encoding="utf-8")

    rules = [
        RULE_CATALOG["RULE_001"],
        RULE_CATALOG["RULE_JAKARTA_SERVLET"]
    ]

    # Dry run
    changes = engine.apply_rules_to_file(str(file_path), rules, dry_run=True)
    assert len(changes) == 1
    assert "jakarta.persistence.Entity1" in changes[0].diff_preview
    assert "jakarta.servlet.http.HttpServletRequest" in changes[0].diff_preview
    # File should not be modified yet
    assert "javax.persistence.Entity1" in file_path.read_text(encoding="utf-8")

    # In-place run
    changes2 = engine.apply_rules_to_file(str(file_path), rules, dry_run=False)
    assert len(changes2) == 1
    modified_code = file_path.read_text(encoding="utf-8")
    assert "jakarta.persistence.Entity1" in modified_code
    assert "jakarta.servlet.http.HttpServletRequest" in modified_code
    assert "javax." not in modified_code

def test_apply_plan_and_validate(tmp_path):
    engine = RuleEngine()
    
    # Create a dummy legacy project
    src_dir = tmp_path / "src" / "main" / "java" / "com" / "example"
    src_dir.mkdir(parents=True)
    test_dir = tmp_path / "src" / "test" / "java" / "com" / "example"
    test_dir.mkdir(parents=True)
    
    entity_file = src_dir / "User.java"
    entity_file.write_text(
        "package com.example;\n"
        "import javax.persistence.Entity1;\n"
        "public class User {}\n",
        encoding="utf-8"
    )

    test_file = test_dir / "UserTest.java"
    test_file.write_text(
        "package com.example;\n"
        "import org.junit.Test;\n"
        "import static org.junit.Assert.*;\n"
        "public class UserTest {\n"
        "    @Test\n"
        "    public void test() {}\n"
        "}\n",
        encoding="utf-8"
    )

    pom_file = tmp_path / "pom.xml"
    pom_file.write_text(
        "<project>\n"
        "  <parent>\n"
        "    <groupId>org.springframework.boot</groupId>\n"
        "    <artifactId>spring-boot-starter-parent</artifactId>\n"
        "    <version>2.7.14</version>\n"
        "  </parent>\n"
        "  <properties>\n"
        "    <java.version>1.8</java.version>\n"
        "  </properties>\n"
        "</project>\n",
        encoding="utf-8"
    )

    rules = [
        RULE_CATALOG["RULE_001"],
        RULE_CATALOG["RULE_JUNIT4_TO_JUNIT5_TEST"],
        RULE_CATALOG["RULE_JUNIT4_TO_JUNIT5_ASSERT"],
        RULE_CATALOG["RULE_POM_BOOT_PARENT_34"],
        RULE_CATALOG["RULE_JAVA_VERSION_17"],
        RULE_CATALOG["RULE_SECURITY_MATCHER"]  # Rule that will be skipped (not present)
    ]

    plan = MigrationPlan(
        plan_id="plan_test_001",
        source_version=SpringVersion.BOOT_2_7,
        target_version=SpringVersion.BOOT_3_5,
        rules=rules,
        estimated_changes=len(rules),
        risk_summary={RiskLevel.LOW: 5, RiskLevel.MEDIUM: 1}
    )

    # Execute plan in-place
    result = engine.apply_plan(str(tmp_path), plan, dry_run=False)

    assert result.plan_id == "plan_test_001"
    assert "RULE_001" in result.applied_rules
    assert "RULE_JUNIT4_TO_JUNIT5_TEST" in result.applied_rules
    assert "RULE_POM_BOOT_PARENT_34" in result.applied_rules
    assert "RULE_JAVA_VERSION_17" in result.applied_rules
    assert "RULE_SECURITY_MATCHER" in result.skipped_rules
    assert len(result.file_changes) == 3

    # Check file updates
    assert "jakarta.persistence.Entity1" in entity_file.read_text(encoding="utf-8")
    assert "org.junit.jupiter.api.Test" in test_file.read_text(encoding="utf-8")
    assert "<version>3.4.0</version>" in pom_file.read_text(encoding="utf-8")
    assert "<java.version>17</java.version>" in pom_file.read_text(encoding="utf-8")

    # Validate results
    validation = engine.validate_result(str(tmp_path), result)
    assert validation["valid"] is True
    assert validation["residual_legacy_count"] == 0
    assert validation["files_checked"] >= 3


def test_token_shielding_comments_and_strings():
    engine = RuleEngine()
    rule = RULE_CATALOG["RULE_001"]
    
    code = (
        "package com.example;\n"
        "// Notice: keep javax.persistence.Entity1 commented out for reference\n"
        "/* In ancient times, javax.persistence.Entity1 was used */\n"
        "public class Example {\n"
        '    private String desc = "javax.persistence.Entity1 in string literal";\n'
        "    private javax.persistence.Entity1 entity;\n"
        "}\n"
    )
    
    transformed, count = engine.apply_rule(code, rule, is_java_file=True)
    assert count == 1
    # Line comment shielded
    assert "// Notice: keep javax.persistence.Entity1 commented out" in transformed
    # Block comment shielded
    assert "/* In ancient times, javax.persistence.Entity1 was used */" in transformed
    # String literal shielded
    assert '"javax.persistence.Entity1 in string literal"' in transformed
    # Code token transformed
    assert "private jakarta.persistence.Entity1 entity;" in transformed


def test_ast_spring_mvc_composed_annotations():
    engine = RuleEngine()
    code = (
        "package com.example.api;\n"
        "import org.springframework.web.bind.annotation.RequestMapping;\n"
        "import org.springframework.web.bind.annotation.RequestMethod;\n"
        "import org.springframework.web.bind.annotation.RestController;\n"
        "@RestController\n"
        "public class OrderController {\n"
        '    @RequestMapping(value = "/api/orders", method = RequestMethod.GET)\n'
        "    public List<Order> getOrders() { return null; }\n"
        '    @RequestMapping(path = "/api/orders", method = RequestMethod.POST)\n'
        "    public Order createOrder() { return null; }\n"
        "}\n"
    )
    
    transformed, count = engine.rewrite_spring_mvc_annotations(code)
    assert count == 2
    assert '@GetMapping("/api/orders")' in transformed
    assert '@PostMapping("/api/orders")' in transformed
    assert "@RequestMapping" not in transformed


def test_ast_webmvc_configurer_adapter():
    engine = RuleEngine()
    code = (
        "package com.example.config;\n"
        "import org.springframework.context.annotation.Configuration;\n"
        "import org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter;\n"
        "@Configuration\n"
        "public class WebConfig extends WebMvcConfigurerAdapter {\n"
        "}\n"
    )
    
    transformed, count = engine.rewrite_webmvc_configurer_adapter(code)
    assert count == 2
    assert "public class WebConfig implements WebMvcConfigurer {" in transformed
    assert "org.springframework.web.servlet.config.annotation.WebMvcConfigurer;" in transformed
    assert "WebMvcConfigurerAdapter" not in transformed


def test_syntactic_integrity_protection():
    engine = RuleEngine()
    # Balanced code
    assert engine.validate_syntactic_integrity("class A { void m() {} }", "class A { void m() {} }") is True
    # Corrupted code with missing brace
    assert engine.validate_syntactic_integrity("class A { void m() {} }", "class A { void m() { }") is False
    # Corrupted code with missing paren
    assert engine.validate_syntactic_integrity("foo(bar);", "foo(bar;") is False


def test_apply_plan_does_not_claim_rules_when_atomic_write_fails(tmp_path, monkeypatch):
    engine = RuleEngine()
    source = tmp_path / "Entity.java"
    source.write_text("import javax.persistence.Entity1;", encoding="utf-8")
    rule = RULE_CATALOG["RULE_001"]
    plan = MigrationPlan(
        plan_id="write-failure",
        source_version=SpringVersion.BOOT_2_7,
        target_version=SpringVersion.BOOT_3_5,
        rules=[rule],
        estimated_changes=1,
        risk_summary={RiskLevel.LOW: 1},
    )

    def fail_write(_path, _content):
        raise OSError("injected durable write failure")

    monkeypatch.setattr(engine, "_atomic_write", fail_write)
    result = engine.apply_plan(str(tmp_path), plan, dry_run=False)

    assert result.applied_rules == []
    assert result.failed_rules == [rule.rule_id]
    assert result.file_changes == []
    assert "javax.persistence" in source.read_text(encoding="utf-8")
    assert any("durable write failure" in warning for warning in result.warnings)
