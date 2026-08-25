---
name: recipe-descriptor-introspection
description: 对 Recipe、子 Recipe、参数、数据表、维护者和来源做运行时自描述。 Use for this exact ELMOS Spring Golden Route v2 contract; imported specifications are not runtime or certification evidence.
license: Elmos skill specification; upstream inspiration remains under its original license
metadata:
  batch: '02'
  priority: P0
  source_projects: openrewrite
  spec_version: 1.0.0
  source_compatibility: elmos,codex,claude-code,opencode
  source_package: elmos-spring-golden-route-commercial-skills
  source_version: 2.0.0
  source_id: FOUNDATION-02-recipe-descriptor-introspection
  source_name: recipe-descriptor-introspection
  source_path: skills/recipe-descriptor-introspection/SKILL.md
  source_sha256: sha256:8bc11f927740ab330b890582ce0269d1ff75dea40b4dae8a8d8e875b1e6d0639
  source_contract_sha256: sha256:6cfb87625fee402c2d0d39ac7e9f73cb8c084dcf841a9bfb13c17862347061ff
  source_origin: foundation
  installed_namespace: spring-golden-route-commercial-v2
  implementation_state: SPECIFICATION_IMPORTED
  runtime_evidence_status: NOT_RUN
  customer_evidence_status: NOT_RUN
  external_evidence_status: NOT_RUN
  certification: NOT_CERTIFIED
  side_effects_authorized: false
---

# Recipe Descriptor Introspection

## Goal

对 Recipe、子 Recipe、参数、数据表、维护者和来源做运行时自描述。

## Use when

在 Elmos 需要实现或升级 **Recipe Descriptor Introspection** 相关能力时使用；它不是仅供解释的提示词，而是实现、测试与验收契约。

## Capabilities to implement

- 无需实例化全部逻辑即可浏览目录
- descriptor 包含 displayName/description/tags/options/dataTables
- 可用于搜索、文档和 Agent tool definition
- descriptor 与实际实现做完整性校验

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

- [ ] 定义 `recipe-descriptor-introspection` 的 public interface、input/output/error schemas。
- [ ] 建立 `recipe-descriptor-introspection` 的 capability/feature flags 与版本字段。
- [ ] 实现核心执行路径，并把外部依赖隔离在 adapter/provider 层。
- [ ] 增加 provenance / trace / metric hooks，禁止只写自由文本日志。
- [ ] 补齐幂等性、失败、取消、超时、缓存失效或回滚语义（按本 Skill 适用范围）。
- [ ] 编写 unit、integration、fixture/regression tests。
- [ ] 在 Elmos capability registry 与 Skills Marketplace 注册，并设置生产权限。

## Acceptance criteria

- [ ] 至少覆盖并验收：无需实例化全部逻辑即可浏览目录；以及 descriptor 包含 displayName/description/tags/options/dataTables。
- [ ] 同一 fixture 连续执行两次不得产生非预期二次 diff。
- [ ] 失败时原始源码/输入保持可恢复，且错误包含可定位 provenance。
- [ ] 提供 unit + integration tests，并为关键错误路径提供负例。
- [ ] 输出结构化 metrics：成功率、失败类型、wall-clock 与资源/Token 成本（适用时）。

## Elmos integration points

- `transformation-engine`
- `rule-dsl`
- `mutation-dsl`

## Upstream inspiration

- openrewrite: https://github.com/openrewrite/rewrite @ 4bc18536d99bb86f1ba0f353643de72ef56dd165 (main, Apache-2.0)
- Source areas: `rewrite-core/src/main/java/org/openrewrite/Recipe.java`
- Source areas: `rewrite-core/src/main/java/org/openrewrite/RecipeScheduler.java`
- Source areas: `rewrite-core/src/main/java/org/openrewrite/Result.java`

## Adaptation rule

借鉴行为契约、架构边界和工程机制；不要把上游内部对象模型直接当成 Elmos 的永久公共 API。若复制或修改上游源码，必须单独进行 license/NOTICE/attribution 审核。

## Repository import binding

- Machine contract: `references/contract.json` (`sha256:6cfb87625fee402c2d0d39ac7e9f73cb8c084dcf841a9bfb13c17862347061ff`).
- This installed interface imports the specification only; runtime, customer, and external evidence remain `NOT_RUN`.
- Repository import does not authorize writes, providers, customer operations, commercial claims, or certification.
