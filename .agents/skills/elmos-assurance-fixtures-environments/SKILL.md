---
name: "elmos-assurance-fixtures-environments"
description: "测试数据与原生环境工厂。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。"
implementation_state: "VERIFIED"
metadata:
  source_package: "elmos-assurance-skills"
  source_package_id: "elmos-assurance-skills-v4.0.0"
  source_version: "4.0.0"
  source_path: "skills/elmos-assurance-fixtures-environments/SKILL.md"
  source_sha256: "sha256:1506104941d620d807f776abbfe76258622b34507f8d861b3e538a09a954075b"
  normalized_namespace: "elmos.assurance/v4"
  runtime_module: "engines/assurance-engine/src/elmos_assurance_engine/dispatcher.py"
  runtime_dispatcher: "dispatch_assurance_skill"
  runtime_skill_key: "elmos-assurance-fixtures-environments"
  runtime_evidence: "LOCAL_HANDLER_BOUND_EXECUTED"
  external_evidence: "NOT_RUN"
  certification: "READY_FOR_EXTERNAL_GATE"
---

## Trusted Repository Runtime Wrapper

This installed Skill is a repository-owned dispatch interface for `elmos-assurance-fixtures-environments` from package `elmos-assurance-skills-v4.0.0`.

### Normative Authority & Fail-Closed Boundary
- Source contract: `.elmos/assurance-package-v4.0.0/skills/elmos-assurance-fixtures-environments/SKILL.md`
- Implementation tasks: `.elmos/assurance-package-v4.0.0/skills/elmos-assurance-fixtures-environments/implementation.yaml`
- Acceptance criteria: `.elmos/assurance-package-v4.0.0/skills/elmos-assurance-fixtures-environments/acceptance.yaml`
- Runtime handler: Bound allowlisted handler under `engines/assurance-engine/`

Any missing environment, dependency, or signature defaults to `NOT_RUN` / `INCONCLUSIVE`.
