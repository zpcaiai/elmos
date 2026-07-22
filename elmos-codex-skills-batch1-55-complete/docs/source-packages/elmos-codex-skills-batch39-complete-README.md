# ELMOS Codex Skills — Batch 39 Complete

## Package contents

This package contains **48 implementation Skills**:

- **Batch 39A — 16 Skills:** Financial、Billing与Commercial Operations
- **Batch 39B — 16 Skills:** Payment、Treasury与Financial Risk Operations
- **Batch 39C — 16 Skills:** Finance Analytics、Planning与Unit Economics

## Directory layout

```text
agent-skills/runtime/<skill-name>/SKILL.md
docs/batch-39a-overview.md
docs/batch-39b-overview.md
docs/batch-39c-overview.md
references/
templates/
scripts/
AGENTS.md
manifest.json
install.sh
validate.sh
```

## Install

```bash
./install.sh ~/.codex/skills
```

The installer copies each Skill directory into the target directory and rejects duplicate destination names unless `--overwrite` is passed.

## Validate

```bash
./validate.sh
```

The validator checks:

- exactly 48 Skill directories exist;
- YAML frontmatter names match directory names and manifest entries;
- required sections exist;
- Skill names are unique;
- shell scripts pass syntax checking;
- obvious secret material is absent.

## Architecture

```text
39A  Usage → Pricing → Billing → Tax → AR → Revenue → Subledger
  ↓
39B  Payment → Settlement → Cash Application → Treasury → Fraud
  ↓
39C  Metrics → Margin → Allocation → Planning → Profitability → Cockpit
```

## Trust boundary

This package is implementation guidance. Static package validation does not certify production tax treatment, accounting conclusions, payment providers, bank integrations, financial close or management reporting. Each Skill must earn completion through its own tests and evidence in the target ELMOS repository.
