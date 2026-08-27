---
id: 33-unknown-semantics-ledger
title: 未知语义债务账本
version: 1.0.0
phase: semantic-model
priority: P0
requires:
- 31-legacy-web-semantic-ir
produces:
- unknown-semantics-ledger
idempotent: true
resumable: true
---

# 未知语义债务账本

## 目标

把无法可靠解释、证据冲突、动态反射/脚本和环境缺失显式登记，禁止以猜测冒充已迁移事实。

本技能属于 **证据图、Semantic IR 与风险模型**。阶段目标：将异构事实转成稳定、可比较、可生成、可验证的中间表示。

## 输入

- `31-legacy-web-semantic-ir`

同时读取：

- `job-contract` 与不可变 `policy-snapshot`
- 当前 `repository-snapshot`、Environment/Attachment authority
- 上游 artifact 的 hash、schemaVersion、producerVersion
- 已存在的 unknown、risk、decision 与 checkpoint

## 输出

- `unknown-semantics-ledger`

每个输出必须携带：

```yaml
artifactId: <uuid>
schemaVersion: <version>
producerSkill: 33-unknown-semantics-ledger
producerVersion: 1.0.0
inputHashes: []
policySnapshotHash: <sha256>
environmentId: <environment>
evidenceRefs: []
confidence: 0.0
createdAt: <RFC3339>
```

## 硬性不变量

- IR 节点必须可追溯到至少一条 evidence；推断事实必须标注 inference。
- 冲突证据不得静默覆盖。
- 未知项必须可量化并影响认证等级。
- IR 版本升级必须提供向后兼容或迁移器。

## 执行步骤

1. 读取各适配器模型并执行 schema/version 检查。
2. 按稳定标识合并同一实体的多来源证据。
3. 保留冲突、推断和环境差异。
4. 计算覆盖率、未知项和风险派生数据。
5. 发布可供 planner/generator/oracle 消费的规范化 artifact。
6. unknown 分类：missing environment、dynamic reflection、native code、script、encrypted config、unreplayed path、evidence conflict。
7. 记录影响范围、严重度、阻断 gate、建议补证方式和 owner。
8. 任何自动推测必须保持 `status=inferred`，不得自动升级为 confirmed。
9. 未知项关闭必须附新 evidence。

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
