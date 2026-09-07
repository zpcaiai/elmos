---
id: 02-reproducible-repository-snapshot
title: 可复现仓库快照
version: 1.0.0
phase: control-plane
priority: P0
requires:
- 01-job-contract-and-policy-resolver
produces:
- repository-snapshot
- reproduction-lock
idempotent: true
resumable: true
---

# 可复现仓库快照

## 目标

固定 Git、子模块、LFS、构建依赖、制品仓库、JDK、容器镜像、环境配置和数据库基线，形成可重放输入。

本技能属于 **控制面与长任务执行**。阶段目标：保证任务契约、权限、可复现性、幂等性、恢复性以及 Elmos 自身运行时 ETA/成本可见。

## 输入

- `01-job-contract-and-policy-resolver`

同时读取：

- `job-contract` 与不可变 `policy-snapshot`
- 当前 `repository-snapshot`、Environment/Attachment authority
- 上游 artifact 的 hash、schemaVersion、producerVersion
- 已存在的 unknown、risk、decision 与 checkpoint

## 输出

- `repository-snapshot`
- `reproduction-lock`

每个输出必须携带：

```yaml
artifactId: <uuid>
schemaVersion: <version>
producerSkill: 02-reproducible-repository-snapshot
producerVersion: 1.0.0
inputHashes: []
policySnapshotHash: <sha256>
environmentId: <environment>
evidenceRefs: []
confidence: 0.0
createdAt: <RFC3339>
```

## 硬性不变量

- 任何有副作用的步骤必须绑定具体 Environment/Attachment 权限快照。
- 重复执行同一 step_id 不得产生额外副作用。
- 取消后不得继续发布新 change set；恢复必须从最后一个已提交检查点开始。
- ETA 必须表示机器 wall-clock 时间，不得以人工人天替代。

## 执行步骤

1. 读取并验证输入契约与权限上下文。
2. 计算 deterministic step/input hash，查询可复用检查点。
3. 执行任务并持续写入结构化事件、指标和 artifact。
4. 在提交前运行本技能自检与策略门。
5. 原子发布输出并更新下游 DAG。
6. 记录 Git SHA、submodule SHA、LFS object、dirty patch、文件哈希和大小。
7. 固定 Maven/Gradle/Ant/JDK/Node/容器版本、镜像 digest、仓库 mirror 和离线依赖。
8. 采集可构建与不可构建基线；源系统无法构建时仍保留运行镜像/二进制与 trace 证据。
9. 敏感配置只存 secret reference，不复制明文。

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
