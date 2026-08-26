---
id: 23-jsp-taglib-and-view-semantics
title: JSP、Taglib 与视图语义恢复
version: 1.0.0
phase: semantic-recovery
priority: P0
requires:
- 11-framework-and-version-fingerprinting
- 12-runtime-deployment-topology
produces:
- view-semantics-ir
- view-dependency-graph
idempotent: true
resumable: true
---

# JSP、Taglib 与视图语义恢复

## 目标

解析 JSP/JSTL/TLD/custom tag/Tiles/FreeMarker 等视图依赖、scope、表达式、动态 include、标签副作用和输出编码。

本技能属于 **遗留运行时语义恢复**。阶段目标：恢复请求生命周期、状态、导航、安全、事务、副作用、视图与并发语义，而非做表面 API 替换。

## 输入

- `11-framework-and-version-fingerprinting`
- `12-runtime-deployment-topology`

同时读取：

- `job-contract` 与不可变 `policy-snapshot`
- 当前 `repository-snapshot`、Environment/Attachment authority
- 上游 artifact 的 hash、schemaVersion、producerVersion
- 已存在的 unknown、risk、decision 与 checkpoint

## 输出

- `view-semantics-ir`
- `view-dependency-graph`

每个输出必须携带：

```yaml
artifactId: <uuid>
schemaVersion: <version>
producerSkill: 23-jsp-taglib-and-view-semantics
producerVersion: 1.0.0
inputHashes: []
policySnapshotHash: <sha256>
environmentId: <environment>
evidenceRefs: []
confidence: 0.0
createdAt: <RFC3339>
```

## 硬性不变量

- 执行顺序、短路条件和 before/after 行为必须保留。
- forward、include、redirect、chain、error dispatch 不得混为一类。
- request/session/application/thread/static 等作用域必须显式。
- 所有语义结论必须链接证据、置信度与适用环境。

## 执行步骤

1. 定位框架入口、配置与自定义扩展点。
2. 展开实际执行顺序、条件、短路和 after/unwind。
3. 识别状态读写、外部副作用、异常和导航。
4. 将结论写入专用 IR，并链接 evidence。
5. 把动态或证据不足项写入 unknown ledger。
6. 构建 JSP include/tag/file/EL/bean/request-attribute 依赖图。
7. 解析 TLD 与 Tag/BodyTag/SimpleTag 生命周期，识别数据库/会话等不应存在但现实存在的标签副作用。
8. 恢复 Tiles definition 继承、动态模板和 locale/message resources。
9. 区分纯展示 view 与包含业务/副作用的 active view。

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
