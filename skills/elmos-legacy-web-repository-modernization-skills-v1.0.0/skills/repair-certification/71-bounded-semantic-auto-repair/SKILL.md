---
id: 71-bounded-semantic-auto-repair
title: 有界语义自动修复
version: 1.0.0
phase: repair-certification
priority: P0
requires:
- 58-idempotent-change-set-commit
- 70-mismatch-classification
produces:
- repair-change-sets
- repair-evidence
idempotent: true
resumable: true
---

# 有界语义自动修复

## 目标

基于最小影响范围、证据约束和风险上限生成修复；每次只改一个根因，限制循环次数并禁止无证据大范围重写。

本技能属于 **自动修复、切流与生产认证**。阶段目标：将差异转为最小修复，执行影响面回归，形成可审计证据并决定是否可生产切换。

## 输入

- `58-idempotent-change-set-commit`
- `70-mismatch-classification`

同时读取：

- `job-contract` 与不可变 `policy-snapshot`
- 当前 `repository-snapshot`、Environment/Attachment authority
- 上游 artifact 的 hash、schemaVersion、producerVersion
- 已存在的 unknown、risk、decision 与 checkpoint

## 输出

- `repair-change-sets`
- `repair-evidence`

每个输出必须携带：

```yaml
artifactId: <uuid>
schemaVersion: <version>
producerSkill: 71-bounded-semantic-auto-repair
producerVersion: 1.0.0
inputHashes: []
policySnapshotHash: <sha256>
environmentId: <environment>
evidenceRefs: []
confidence: 0.0
createdAt: <RFC3339>
```

## 硬性不变量

- 自动修复必须有界、最小化，并能回滚。
- 同一根因连续失败达到上限后必须停止扩散式修改。
- 存在 critical unknown 或关键安全/事务差异时不得签发 E5。
- 切流必须有可执行回滚路径与自动触发条件。

## 执行步骤

1. 聚合差异、风险、source map 和历史修复。
2. 定位最早分叉与共享根因。
3. 执行有界修复或切流/认证动作。
4. 运行影响面回归及必要的全量验证。
5. 更新证据包、未知账本和认证状态。
6. 先生成最小假设，再产生最小 patch 和可证伪测试。
7. 禁止在关键安全/事务逻辑上无 evidence 猜测。
8. 每轮记录 before/after mismatch、影响面和回滚 patch。
9. 超过 iteration/budget 或风险上限，转 unknown/decision，不进行扩散式重构。

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

## Elmos 集成钩子

- 事件：`skill.started`、`artifact.produced`、`evidence.conflict`、`risk.raised`、`skill.completed`、`skill.failed`
- 指标：`wall_clock_ms`、`cache_hit`、`evidence_coverage`、`unknown_count`、`critical_risk_count`
- Trace 属性：`job_id`、`step_id`、`transformation_unit_id`、`repository_snapshot_id`、`policy_hash`
- Artifact 默认写入对象存储；查询索引与状态写入 PostgreSQL；大对象不得直接塞入任务表
