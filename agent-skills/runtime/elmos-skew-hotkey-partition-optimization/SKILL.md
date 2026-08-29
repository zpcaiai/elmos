---
name: skew-hotkey-partition-optimization
description: Use this skill when Elmos must 检测数据倾斜与 Hot Key，生成盐化、重分区、预聚合和容量策略。 The execution must use typed contracts, version-pinned environments, independent verification, evidence capture, and rollback.
license: Proprietary-Elmos-Commercial
compatibility: Elmos Proof-Driven Agentic Harness v3+; K3 Dataflow Compiler + K6 Data Product Verification; policy, evidence, workspace and verification services required.
metadata:
  version: "3.0.0"
  pack: 25-data-engineering-lakehouse-analytics
  priority: P0
  business-line: data-engineering
  risk-class: critical
  exposure: atomic-registry-only
allowed-tools: data.profile pipeline.parse semantic.transform pipeline.execute quality.verify lineage.emit evidence.write
---

# skew-hotkey-partition-optimization

## 能力目标

检测数据倾斜与 Hot Key，生成盐化、重分区、预聚合和容量策略。

该能力属于 **Data Engineering, Lakehouse & Analytics / 大数据与湖仓**，必须作为仓库级、可重放、可度量、可回滚的生产动作执行，不得降级为一次性 Prompt 技巧。

## 应触发场景

- 任务事实、技术栈和验收标准与上述能力目标一致；
- 租户、仓库、数据、模型、工具与目标环境均已授权并锁定版本；
- 需要生成代码、补丁、配置、数据、测试、部署或认证证据；
- 注册表确认依赖、兼容矩阵、风险等级和执行资源满足要求。

## 不应触发场景

- 仅解释概念、改写文本或进行不访问资产的讨论；
- 缺少源基线、目标契约、独立验证环境或可用回滚点；
- 请求删除测试、扩大权限、伪造证据、跨租户读取或绕过审批；
- 更窄、更确定性的 Skill 已能完整覆盖且风险更低。

## 输入契约

- `TaskContract`、租户/项目/仓库/分支/环境身份；
- 版本锁定的源资产、目标能力画像、Semantic IR 或领域基线；
- 功能、行为、性能、安全、隐私、成本和机器 Wall-clock 验收标准；
- 允许的工具、副作用、人工审批、训练授权和回滚边界。

## 执行工作流

1. `inventory-data-platform`：记录输入、决定、工具、环境、产物和失败语义。
2. `define-data-contracts`：记录输入、决定、工具、环境、产物和失败语义。
3. `extract-dataflow-ir`：记录输入、决定、工具、环境、产物和失败语义。
4. `generate-or-migrate-pipelines`：记录输入、决定、工具、环境、产物和失败语义。
5. `replay-and-reconcile`：记录输入、决定、工具、环境、产物和失败语义。
6. `operate-and-chaos-test`：记录输入、决定、工具、环境、产物和失败语义。
7. `certify-data-products`：记录输入、决定、工具、环境、产物和失败语义。


## 必须保持的不变量

- `data-contract-covered`
- `quality-and-lineage-pass`
- `replay-equivalent`
- `recovery-tested`
- `cost-and-sla-acceptable`
- `tenant-boundary-preserved`
- `source-and-target-traceable`
- `no-hidden-test-weakening`
- `no-evidence-fabrication`
- `machine-wall-clock-recorded`


## 输出与 Evidence Contract

- 内容寻址的计划、补丁/生成物、测试、报告和回滚记录；
- Source → Semantic IR → Target 的映射或等价的来源链；
- 模型、Adapter、Skill、知识、工具、镜像、配置与数据版本；
- 机器 Wall-clock、Token、GPU、构建、测试、存储、网络和人工审批成本；
- 通过、失败、不确定、豁免、残余风险和人工接管条件。

最低证据级别：**E3**。硬门：data-contract-covered, quality-and-lineage-pass, replay-equivalent, recovery-tested, cost-and-sla-acceptable。

## 失败、阻断与回滚

任何确定性硬门、授权、租户隔离、数据权利、关键安全、行为等价或回滚门失败时，状态必须为 `blocked`；保留可诊断工作区和证据，恢复版本化检查点并执行补偿。不得以模型自评覆盖硬失败。

## 学习与资产沉淀

执行轨迹默认进入 Bronze Experience；只有经过独立验证、去重、权利检查、人工接受且达到 Gold 数据门后，才能在明确授权下用于租户 Adapter。客户数据默认禁止进入全局训练。

## 实现状态

本 Skill 在本包中达到 `specification-ready`：契约、触发、权限、证据、回滚和评测要求已定义；具体 Runtime Adapter、解析器、转换器、验证器或连接器仍需按照实施路线编码并达到目标认证级别。
