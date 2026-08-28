# Validation Report — elmos-pricing-billing-skills-v1.0.0

## Scope

This report covers the distributable skill package itself. It does **not** claim that any target Elmos application has implemented the billing system.

## Expected release inventory

- Skills: 18
- Batches: 54
- Requirements: 180
- Scenario tests: 50
- Agent Skills frontmatter: `name` and `description`, names matching parent directories
- Host paths: `.agents/skills` and `.claude/skills`
- Plugin manifests: `.codex-plugin/plugin.json`, `.claude-plugin/plugin.json`

## Validation command

```bash
./validate.sh
```

## Checks performed

- YAML frontmatter and skill naming constraints
- Required SKILL.md sections and relative resource references
- Skill and batch dependency DAGs
- Manifest/count/traceability consistency
- JSON and YAML syntax where PyYAML is available
- Safe paths, no symlinks, executable scripts
- Controlled-file SHA-256 verification
- Quote-calculator unit tests, BYOK split and ETA separation
- Reference quote CLI execution

## Result

`PASS` after generation in the controlled build environment. Re-run `./validate.sh` after extraction and before installation. Archive round-trip hashes are recorded in the external release checksum file.

## Explicit non-claims

- Example prices are draft and not production-approved.
- Reference SQL/API/event files require adaptation to the target repository.
- Engineering controls do not replace jurisdiction-specific legal, tax, accounting, PCI, privacy or regulatory review.
- Package validation is not product E1–E5 certification.
