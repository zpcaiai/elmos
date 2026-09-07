---
id: 51-struts1-to-springmvc-generator
title: Struts 1→Spring MVC 生成器
version: 1.0.0
phase: transformation
priority: P0
requires:
- 20-struts1-lifecycle-recovery
- 31-legacy-web-semantic-ir
- 43-compatibility-shim-synthesis
- 50-deterministic-ast-and-config-rewrite
produces:
- struts1-target-changes
idempotent: true
resumable: true
---

# Struts 1→Spring MVC 生成器

## 目标

从 Struts1 pipeline IR 生成 Controller、DTO/ModelAttribute、Validator、Interceptor/Filter、ExceptionHandler 和导航桥。

本技能属于 **确定性转换与代码生成**。阶段目标：依据 IR 生成 Spring Boot 4 代码、配置、依赖、视图与测试，并保持变更可重复、可溯源。

## 输入

- `20-struts1-lifecycle-recovery`
- `31-legacy-web-semantic-ir`
- `43-compatibility-shim-synthesis`
- `50-deterministic-ast-and-config-rewrite`

同时读取：

- `job-contract` 与不可变 `policy-snapshot`
- 当前 `repository-snapshot`、Environment/Attachment authority
- 上游 artifact 的 hash、schemaVersion、producerVersion
- 已存在的 unknown、risk、decision 与 checkpoint

## 输出

- `struts1-target-changes`

每个输出必须携带：

```yaml
artifactId: <uuid>
schemaVersion: <version>
producerSkill: 51-struts1-to-springmvc-generator
producerVersion: 1.0.0
inputHashes: []
policySnapshotHash: <sha256>
environmentId: <environment>
evidenceRefs: []
confidence: 0.0
createdAt: <RFC3339>
```

## 硬性不变量

- 优先使用 AST、符号解析和结构化配置改写；禁止 regex-only 的大规模迁移。
- LLM 生成必须受 evidence、IR、目标 API 和差异测试约束。
- 每个目标构造必须记录来源证据和转换原因。
- 同一输入与 policy snapshot 重跑必须产生语义等价且无漂移的结果。

## 执行步骤

1. 验证 recipe 前置条件、目标版本和 source hash。
2. 执行结构化改写/生成，并记录 provenance。
3. 运行 parse、format、compile/static lint。
4. 生成逆操作、source map 和受影响测试集。
5. 以幂等 change set 发布。
6. ActionMapping→RequestMapping；ActionForm→DTO/ModelAttribute，但 reset/validate/scope 由 lifecycle adapter 保持。
7. RequestProcessor hook 按职责拆到 Filter/Interceptor/ArgumentResolver/Advice，保留顺序与短路。
8. ActionForward 精确生成 forward:/redirect:/ModelAndView 或 compatibility resolver。
9. Action 共享字段在生成前必须通过并发审计。

## 证据规则

- 静态代码、配置、构建结果、运行 trace、测试观察和人工决策使用不同 evidence type。
- `confirmed` 至少需要可重放的一手证据；仅靠名称相似或模型常识只能标记 `inferred`。
- 证据冲突必须保留候选、环境与解析理由，不能后写覆盖。
- 任何会影响路由、安全、事务、session 或副作用的推断都进入风险预算。

## 失败与降级

| 情况 | 动作 |
|---|---|
| 输入 schema/hash 不匹配 | 停止本 step，失效下游，不消费陈旧 artifact |
| 权限不足或 authority 不明确 | fail closed，不执行副作用 |
| 源系统不可构建 | 使用运行镜像、字节码、trace 与配置取证；标记基线限制 |
| 动态语义无法确定 | 写入 unknown ledger，并提升验证/双运行要求 |
| 可重试工具故障 | 保持 fencing token，按预算重试 |
| 结果不可逆或无法验证 | 不提交 change set，不推进认证 |

## 验收清单

- [ ] 输出通过对应 JSON/YAML Schema 或结构契约校验。
- [ ] 所有结论均有 evidence/provenance；无法证明者标记为 inferred/unknown。
- [ ] 重复执行在相同输入与 policy 下不产生语义漂移。
- [ ] P0/critical 风险不得被 warning 或 normalizer 静默降级。
- [ ] 变更必须可逆，且至少通过 parse/compile 或明确记录阻塞原因。

## Elmos 集成钩子

- 事件：`skill.started`、`artifact.produced`、`evidence.conflict`、`risk.raised`、`skill.completed`、`skill.failed`
- 指标：`wall_clock_ms`、`cache_hit`、`evidence_coverage`、`unknown_count`、`critical_risk_count`
- Trace 属性：`job_id`、`step_id`、`transformation_unit_id`、`repository_snapshot_id`、`policy_hash`
- Artifact 默认写入对象存储；查询索引与状态写入 PostgreSQL；大对象不得直接塞入任务表
