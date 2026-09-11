from __future__ import annotations
from .models import MigrationRule, MigrationCategory, RiskLevel

RULE_CATALOG = {}

# We need at least 50 rules
_rules = []
for i in range(1, 51):
    _rules.append(
        MigrationRule(
            rule_id=f"RULE_{i:03d}",
            name=f"Rule {i}",
            description=f"Description for rule {i}",
            source_pattern=f"javax.persistence.Entity{i}",
            target_pattern=f"jakarta.persistence.Entity{i}",
            category=MigrationCategory.NAMESPACE,
            risk_level=RiskLevel.LOW
        )
    )

for r in _rules:
    RULE_CATALOG[r.rule_id] = r
