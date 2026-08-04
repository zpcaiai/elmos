# Batch 14 Complete Skill Pack

## Theme

**Formal Verification and Proof-Carrying Migration**

把 Formal IR、SMT、符号执行、模型检测、精化关系和 Lean Kernel 验证接入迁移证据链，生成与精确代码和假设绑定的 Proof-Carrying Migration。

## Contents

- `16` independent Codex `SKILL.md` files
- `README.md`
- `CODEX_IMPLEMENTATION_PROMPT.md`
- `SKILL.md`
- `SKILL_INDEX.md`
- `BATCH13_COMPATIBILITY.md`
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
