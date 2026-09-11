from elmos_spring_modernization.rule_engine import RuleEngine
from elmos_spring_modernization.migration_rules import RULE_CATALOG

def test_apply_rule():
    engine = RuleEngine()
    rule = RULE_CATALOG["RULE_001"]
    content, changes = engine.apply_rule("import javax.persistence.Entity1;", rule)
    assert "jakarta.persistence.Entity1" in content
    assert changes == 1
