---
name: lockfile-accuracy-contract
description: 生成锁文件必须满足可验证、可部署、真哈希和 fail-loud 契约。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos skill specification; upstream inspiration remains under its original license
metadata:
  batch: '04'
  priority: P0
  source_projects: openrewrite
  spec_version: 1.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: FOUNDATION-04-lockfile-accuracy-contract
  source_name: lockfile-accuracy-contract
  source_path: skills/lockfile-accuracy-contract/SKILL.md
  source_sha256: sha256:2b588e377781a43732a2cf4bd4f0bd8f6e88aa275c3a06e28d4d799b2f25c638
  source_contract_sha256: sha256:6da715f0b7c90037f8ecab4183142393c496f05faebb9bcd5fa19f2b92095fe8
  source_origin: foundation
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Lockfile Accuracy Contract

## Goal

生成锁文件必须满足可验证、可部署、真哈希和 fail-loud 契约。

## Use when

在 Elmos 需要实现或升级 **Lockfile Accuracy Contract** 相关能力时使用；它不是仅供解释的提示词，而是实现、测试与验收契约。

## Capabilities to implement

- 目标 package manager 的 verify/deploy 等价检查通过
- artifact digest 来自可信索引
- 内部 dependency constraints 自洽
- 无法证明正确时不输出新 lock

## Non-negotiable contract

- 输入、输出和失败必须有可序列化 schema。
- 确定性逻辑相同输入 + 相同版本必须产生相同结果。
- 任何源码修改必须能生成 before/after 与 provenance。
- 不允许静默丢失语义、格式、错误或未支持能力。

## Execution workflow

1. Detect：识别目标语言/仓库/版本/能力与输入边界。
2. Model：构建或查询语义/结构化中间表示，不直接从文本猜测。
3. Execute：执行确定性转换/查询；能力不足时返回显式 unsupported。
4. Verify：parse/print、diff、compile/test 或 schema 校验。
5. Record：保存 provenance、metrics、data tables 与 cache fingerprint。

## Implementation tasks

- [ ] 定义 `lockfile-accuracy-contract` 的 public interface、input/output/error schemas。
- [ ] 建立 `lockfile-accuracy-contract` 的 capability/feature flags 与版本字段。
- [ ] 实现核心执行路径，并把外部依赖隔离在 adapter/provider 层。
- [ ] 增加 provenance / trace / metric hooks，禁止只写自由文本日志。
- [ ] 补齐幂等性、失败、取消、超时、缓存失效或回滚语义（按本 Skill 适用范围）。
- [ ] 编写 unit、integration、fixture/regression tests。
- [ ] 在 Elmos capability registry 与 Skills Marketplace 注册，并设置生产权限。

## Acceptance criteria

- [ ] 至少覆盖并验收：目标 package manager 的 verify/deploy 等价检查通过；以及 artifact digest 来自可信索引。
- [ ] 同一 fixture 连续执行两次不得产生非预期二次 diff。
- [ ] 失败时原始源码/输入保持可恢复，且错误包含可定位 provenance。
- [ ] 提供 unit + integration tests，并为关键错误路径提供负例。
- [ ] 输出结构化 metrics：成功率、失败类型、wall-clock 与资源/Token 成本（适用时）。

## Elmos integration points

- `build-intelligence`
- `verification-engine`
- `evidence-store`

## Upstream inspiration

- openrewrite: https://github.com/openrewrite/rewrite @ 4bc18536d99bb86f1ba0f353643de72ef56dd165 (main, Apache-2.0)
- Source areas: `doc/adr/0009-native-python-lock-regeneration.md`
- Source areas: `doc/adr/0010-native-uv-lock-delta-resolution.md`
- Source areas: `doc/adr/0011-native-node-lock-regeneration.md`
- Source areas: `rewrite-java-tck/`
- Source areas: `rewrite-test/`
- Source areas: `rewrite-benchmarks/`

## Adaptation rule

借鉴行为契约、架构边界和工程机制；不要把上游内部对象模型直接当成 Elmos 的永久公共 API。若复制或修改上游源码，必须单独进行 license/NOTICE/attribution 审核。

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:6da715f0b7c90037f8ecab4183142393c496f05faebb9bcd5fa19f2b92095fe8`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
