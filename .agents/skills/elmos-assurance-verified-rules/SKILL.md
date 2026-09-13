---
name: "elmos-assurance-verified-rules"
description: "带证据变换规则注册中心。用于在现有Elmos中实现本模块及其自动测试；不用于跳过原生验证、改变认证范围或直接生产签发。"
implementation_state: "VERIFIED"
metadata:
  source_package: "elmos-assurance-skills"
  source_package_id: "elmos-assurance-skills-v4.0.0"
  source_version: "4.0.0"
  source_path: "skills/elmos-assurance-verified-rules/SKILL.md"
  source_sha256: "sha256:01c4251589ba0a55a7501af2dedffcbd79f257b027f954c4c0e0cd944189eaa6"
  normalized_namespace: "elmos.assurance/v4"
  runtime_module: "engines/assurance-engine/src/elmos_assurance_engine/dispatcher.py"
  runtime_dispatcher: "dispatch_assurance_skill"
  runtime_skill_key: "elmos-assurance-verified-rules"
  runtime_evidence: "LOCAL_HANDLER_BOUND_EXECUTED"
  external_evidence: "NOT_RUN"
  certification: "READY_FOR_EXTERNAL_GATE"
---

## Trusted Repository Runtime Wrapper

This installed Skill is a repository-owned dispatch interface for `elmos-assurance-verified-rules` from package `elmos-assurance-skills-v4.0.0`.

### Normative Authority & Fail-Closed Boundary
- Source contract: `.elmos/assurance-package-v4.0.0/skills/elmos-assurance-verified-rules/SKILL.md`
- Implementation tasks: `.elmos/assurance-package-v4.0.0/skills/elmos-assurance-verified-rules/implementation.yaml`
- Acceptance criteria: `.elmos/assurance-package-v4.0.0/skills/elmos-assurance-verified-rules/acceptance.yaml`
- Runtime handler: Bound allowlisted handler under `engines/assurance-engine/`

Any missing environment, dependency, or signature defaults to `NOT_RUN` / `INCONCLUSIVE`.
