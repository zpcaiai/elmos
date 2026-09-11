---
name: rpc-process-isolation
description: 跨语言 runtime 做任务级/线程级隔离、超时、清理和死锁防护。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos skill specification; upstream inspiration remains under its original license
metadata:
  batch: '05'
  priority: P0
  source_projects: openrewrite
  spec_version: 1.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: FOUNDATION-05-rpc-process-isolation
  source_name: rpc-process-isolation
  source_path: skills/rpc-process-isolation/SKILL.md
  source_sha256: sha256:d25d7b3f7d3d2b8b6ed3424c16f59cb19442c73845d46c92409a9cbf88a3c2b8
  source_contract_sha256: sha256:1741a47016594af380e5722defa8c0cfa5dd606a6f2d5e9f44c550e4e6e1b38d
  source_origin: foundation
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# RPC Process Isolation

## Goal

跨语言 runtime 做任务级/线程级隔离、超时、清理和死锁防护。

## Use when

在 Elmos 需要实现或升级 **RPC Process Isolation** 相关能力时使用；它不是仅供解释的提示词，而是实现、测试与验收契约。

## Capabilities to implement

- 每个并发单元拥有隔离 runtime 或严格租约
- RPC 测试强制 timeout
- 进程崩溃不污染其它 task
- 临时工作目录和句柄在 run 完成后回收

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

- [ ] 定义 `rpc-process-isolation` 的 public interface、input/output/error schemas。
- [ ] 建立 `rpc-process-isolation` 的 capability/feature flags 与版本字段。
- [ ] 实现核心执行路径，并把外部依赖隔离在 adapter/provider 层。
- [ ] 增加 provenance / trace / metric hooks，禁止只写自由文本日志。
- [ ] 补齐幂等性、失败、取消、超时、缓存失效或回滚语义（按本 Skill 适用范围）。
- [ ] 编写 unit、integration、fixture/regression tests。
- [ ] 在 Elmos capability registry 与 Skills Marketplace 注册，并设置生产权限。

## Acceptance criteria

- [ ] 至少覆盖并验收：每个并发单元拥有隔离 runtime 或严格租约；以及 RPC 测试强制 timeout。
- [ ] 同一 fixture 连续执行两次不得产生非预期二次 diff。
- [ ] 失败时原始源码/输入保持可恢复，且错误包含可定位 provenance。
- [ ] 提供 unit + integration tests，并为关键错误路径提供负例。
- [ ] 输出结构化 metrics：成功率、失败类型、wall-clock 与资源/Token 成本（适用时）。

## Elmos integration points

- `repository-intelligence`
- `cache-subsystem`
- `cross-language-runtime`

## Upstream inspiration

- openrewrite: https://github.com/openrewrite/rewrite @ 4bc18536d99bb86f1ba0f353643de72ef56dd165 (main, Apache-2.0)
- Source areas: `doc/adr/0008-rpc-data-table-stores.md`
- Source areas: `.moderne/context/`
- Source areas: `rewrite-core/src/main/java/org/openrewrite/rpc/`

## Adaptation rule

借鉴行为契约、架构边界和工程机制；不要把上游内部对象模型直接当成 Elmos 的永久公共 API。若复制或修改上游源码，必须单独进行 license/NOTICE/attribution 审核。

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:1741a47016594af380e5722defa8c0cfa5dd606a6f2d5e9f44c550e4e6e1b38d`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
