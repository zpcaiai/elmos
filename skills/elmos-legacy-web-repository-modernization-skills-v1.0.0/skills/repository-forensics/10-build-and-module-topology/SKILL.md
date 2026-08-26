---
id: 10-build-and-module-topology
title: 构建与模块拓扑恢复
version: 1.0.0
phase: repository-forensics
priority: P0
requires:
- 02-reproducible-repository-snapshot
produces:
- build-topology
- module-dag
- generated-source-map
idempotent: true
resumable: true
---

# 构建与模块拓扑恢复

## 目标

识别 Maven/Gradle/Ant/Ivy、自定义脚本、EAR/WAR/JAR、父子 POM、生成源码、profile、插件和模块依赖顺序。

本技能属于 **仓库取证与有效运行配置恢复**。阶段目标：从多模块构建、容器、配置叠加和混合框架中恢复系统实际可执行拓扑。

## 输入

- `02-reproducible-repository-snapshot`

同时读取：

- `job-contract` 与不可变 `policy-snapshot`
- 当前 `repository-snapshot`、Environment/Attachment authority
- 上游 artifact 的 hash、schemaVersion、producerVersion
- 已存在的 unknown、risk、decision 与 checkpoint

## 输出

- `build-topology`
- `module-dag`
- `generated-source-map`

每个输出必须携带：

```yaml
artifactId: <uuid>
schemaVersion: <version>
producerSkill: 10-build-and-module-topology
producerVersion: 1.0.0
inputHashes: []
policySnapshotHash: <sha256>
environmentId: <environment>
evidenceRefs: []
confidence: 0.0
createdAt: <RFC3339>
```

## 硬性不变量

- 不得只根据文件名或单一依赖判断框架使用情况。
- 必须区分声明配置、有效配置和运行时观察。
- web.xml、web-fragment、注解和程序化注册必须按规范优先级合并。
- 任何未能复现的模块必须进入 unknown-semantics ledger。

## 执行步骤

1. 静态扫描结构化文件、源码符号和依赖。
2. 从构建/运行观测补充实际使用事实。
3. 合并多来源证据并检测冲突。
4. 输出有效模型、置信度和未决项。
5. 用最小可复现实验验证高风险推断。
6. 同时解析 pom.xml、settings/profile、Gradle settings/build、build.xml、脚本与 CI。
7. 恢复 reactor/module DAG、插件执行期、annotation processor、generated source、resource filtering。
8. 区分 compile/test/provided/container-provided 依赖和 EAR/WAR overlay。
9. 运行构建 trace 验证静态推断，并记录 profile 差异。

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
