# Production Skill Lifecycle

1. **Discover**: load metadata only.
2. **Qualify**: license/security/schema/compatibility checks.
3. **Evaluate**: run isolated fixtures and adversarial tests.
4. **Register**: assign immutable SkillVersion and trust tier.
5. **Advertise**: expose name/description/capabilities only.
6. **Activate**: context-aware router selects skill under policy.
7. **Load**: fetch full SKILL.md/resources only on demand.
8. **Execute**: scripts/tools run through sandbox runner.
9. **Observe**: every run linked to trace + evidence.
10. **Learn**: failures create candidate fixtures/rules/skills.
11. **Promote**: offline replay -> shadow -> canary -> stable.
12. **Deprecate**: compatibility window + migration plan + revocation.

Remote skills are untrusted by default. Remote executable scripts must never gain execution authority merely because their metadata was discoverable.
