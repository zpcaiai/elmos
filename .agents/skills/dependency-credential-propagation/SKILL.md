---
name: dependency-credential-propagation
description: 把仓库、代理和私有索引凭据作为宿主能力安全传入解析器。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos skill specification; upstream inspiration remains under its original license
metadata:
  batch: '04'
  priority: P0
  source_projects: openrewrite,opencode
  spec_version: 1.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: FOUNDATION-04-dependency-credential-propagation
  source_name: dependency-credential-propagation
  source_path: skills/dependency-credential-propagation/SKILL.md
  source_sha256: sha256:d988a51af3e62a42019e110763c3736208702582a975b24cf17974b13e41fdce
  source_contract_sha256: sha256:d157000519b4d44a14a07a6ac3f6f588a7a7ede7643e3c82f961f95b93ede657
  source_origin: foundation
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Dependency Credential Propagation

## Goal

把仓库、代理和私有索引凭据作为宿主能力安全传入解析器。

## Use when

在 Elmos 需要实现或升级 **Dependency Credential Propagation** 相关能力时使用；它不是仅供解释的提示词，而是实现、测试与验收契约。

## Capabilities to implement

- 配置优先级显式且可审计
- 凭据不写入锁文件、日志或模型上下文
- 按 host/scopes 最小授权
- 所有网络访问经统一 transport/policy layer

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

- [ ] 定义 `dependency-credential-propagation` 的 public interface、input/output/error schemas。
- [ ] 建立 `dependency-credential-propagation` 的 capability/feature flags 与版本字段。
- [ ] 实现核心执行路径，并把外部依赖隔离在 adapter/provider 层。
- [ ] 增加 provenance / trace / metric hooks，禁止只写自由文本日志。
- [ ] 补齐幂等性、失败、取消、超时、缓存失效或回滚语义（按本 Skill 适用范围）。
- [ ] 编写 unit、integration、fixture/regression tests。
- [ ] 在 Elmos capability registry 与 Skills Marketplace 注册，并设置生产权限。

## Acceptance criteria

- [ ] 至少覆盖并验收：配置优先级显式且可审计；以及 凭据不写入锁文件、日志或模型上下文。
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
- opencode: https://github.com/anomalyco/opencode @ ba72a6ff2b62aaf614b8e745193e86a51be6142c (dev, MIT)
- Source areas: `doc/adr/0009-native-python-lock-regeneration.md`
- Source areas: `doc/adr/0010-native-uv-lock-delta-resolution.md`
- Source areas: `doc/adr/0011-native-node-lock-regeneration.md`
- Source areas: `rewrite-java-tck/`
- Source areas: `rewrite-test/`
- Source areas: `rewrite-benchmarks/`

## Adaptation rule

借鉴行为契约、架构边界和工程机制；不要把上游内部对象模型直接当成 Elmos 的永久公共 API。若复制或修改上游源码，必须单独进行 license/NOTICE/attribution 审核。

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:d157000519b4d44a14a07a6ac3f6f588a7a7ede7643e3c82f961f95b93ede657`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
