---
id: 66-observability-and-trace-correlation
title: 可观测性与 Trace 关联
version: 1.0.0
phase: verification
priority: P0
requires:
- 03-checkpoint-resume-cancel
- 62-differential-http-and-view-oracle
produces:
- trace-correlation-index
idempotent: true
resumable: true
---

# 可观测性与 Trace 关联

## 目标

用统一 request/sequence/side-effect correlation id 对齐 legacy 与 target trace，输出可定位到 IR/源文件的差异证据。

本技能属于 **静态、动态与差分验证**。阶段目标：证明源系统与目标系统在允许的归一化和显式 hardening delta 之外行为等价。

## 输入

- `03-checkpoint-resume-cancel`
- `62-differential-http-and-view-oracle`

同时读取：

- `job-contract` 与不可变 `policy-snapshot`
- 当前 `repository-snapshot`、Environment/Attachment authority
- 上游 artifact 的 hash、schemaVersion、producerVersion
- 已存在的 unknown、risk、decision 与 checkpoint

## 输出

- `trace-correlation-index`

每个输出必须携带：

```yaml
artifactId: <uuid>
schemaVersion: <version>
producerSkill: 66-observability-and-trace-correlation
producerVersion: 1.0.0
inputHashes: []
policySnapshotHash: <sha256>
environmentId: <environment>
evidenceRefs: []
confidence: 0.0
createdAt: <RFC3339>
```

## 硬性不变量

- 编译通过不是行为等价。
- 任何 normalizer 必须显式、版本化、双向适用且不得掩盖业务差异。
- 状态性流程必须按请求序列验证，不能只比较单个 HTTP 响应。
- 关键数据库写入、事务和安全路径要求 100% 证据覆盖。

## 执行步骤

1. 固定 fixture、环境、时钟、locale、随机种子和依赖 stub。
2. 运行 legacy 与 target 的同一契约/序列。
3. 采集 HTTP、状态、DB、effect、trace 和性能观察。
4. 应用经策略批准的归一化并分类差异。
5. 发布证据充分的 pass/fail/unknown 结果。
6. 为 legacy 与 target 注入同一 correlation/sequence id，不改变业务。
7. trace span 链接 endpoint/pipeline/effect/source-map。
8. 输出首个分叉点，而不仅是最终响应差异。
9. 日志中敏感数据按策略脱敏。

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
- [ ] 报告必须同时给出覆盖分母、已验证数量、未知数量与差异数量。

## Elmos 集成钩子

- 事件：`skill.started`、`artifact.produced`、`evidence.conflict`、`risk.raised`、`skill.completed`、`skill.failed`
- 指标：`wall_clock_ms`、`cache_hit`、`evidence_coverage`、`unknown_count`、`critical_risk_count`
- Trace 属性：`job_id`、`step_id`、`transformation_unit_id`、`repository_snapshot_id`、`policy_hash`
- Artifact 默认写入对象存储；查询索引与状态写入 PostgreSQL；大对象不得直接塞入任务表
