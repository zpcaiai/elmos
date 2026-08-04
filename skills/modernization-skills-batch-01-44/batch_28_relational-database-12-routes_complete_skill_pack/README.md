# Batch 28 Complete Skill Pack

## Theme

**Oracle, SQL Server, MySQL and PostgreSQL 12 Directional Route Packs**

为 Oracle、SQL Server、MySQL、PostgreSQL 的全部 12 条有向路线建立版本化 Route Pack，覆盖 Schema、SQL、Routine、Data、CDC、Dual Run、性能、切换和回退。

## Contents

- `16` independent Codex `SKILL.md` files
- `README.md`
- `CODEX_IMPLEMENTATION_PROMPT.md`
- `SKILL.md`
- `SKILL_INDEX.md`
- `BATCH27_COMPATIBILITY.md`
- `IMPLEMENTATION_CHECKLIST.md`
- `VALIDATION_REPORT.md`
- `PACKAGE_MANIFEST.json`
- versioned schemas, policies, examples, tests, installer and validator

## Install

```bash
./install.sh ~/.codex/skills
```

## Validate

```bash
./validate.sh
```

## Trust Boundary

This package is an implementation-ready specification and deterministic static-validation toolkit. Static PASS validates package structure, schemas, manifests and conservative gate fixtures. It does not claim the target modernization platform, repositories, databases, providers, clouds or production environments have executed the required runtime certification.
