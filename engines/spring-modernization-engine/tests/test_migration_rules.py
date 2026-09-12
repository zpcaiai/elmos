from elmos_spring_modernization.migration_rules import RULE_CATALOG

def test_rules_loaded():
    assert len(RULE_CATALOG) >= 50
    assert "RULE_001" in RULE_CATALOG
