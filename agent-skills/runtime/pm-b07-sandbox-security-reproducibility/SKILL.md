---
name: pm-b07-sandbox-security-reproducibility
description: "将客户代码、AI生成代码、构建脚本和测试视为不可信工作负载，确保隔离、最小权限、审计和可重现. Precision Migration B07 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Batch 07：沙箱、安全与可复现执行
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b07-sandbox-security-reproducibility`.
- Immutable source identity: `batch-07-sandbox-security-reproducibility` in `precision-migration-b01-44` (B07).
- Runtime adapter: `semantic-recovery-and-ir`; binding state: `DECLARED`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b07-sandbox-security-reproducibility`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Goal

将客户代码、AI生成代码、构建脚本和测试视为不可信工作负载，确保隔离、最小权限、审计和可重现。

## Position in the system

- Phase: `B 源码理解与可信执行底座`
- Included skills: `10`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 发现仓库与环境
2. 使用原生工具提取语义
3. 建立可复现工具链和沙箱
4. 执行最小验证任务
5. 持久化摘要、哈希和证据

## Shared gates

- 不执行未隔离的客户或AI代码
- 工具链版本与镜像必须锁定
- 未能解析的动态语义必须显式标记

## Dispatch rules

- 当任务涉及 **untrusted-code-sandbox** 时，调用 `../pm-b07-untrusted-code-sandbox/SKILL.md`。
- 当任务涉及 **network-egress-policy** 时，调用 `../pm-b07-network-egress-policy/SKILL.md`。
- 当任务涉及 **resource-quota-governor** 时，调用 `../pm-b07-resource-quota-governor/SKILL.md`。
- 当任务涉及 **secret-scope-manager** 时，调用 `../pm-b07-secret-scope-manager/SKILL.md`。
- 当任务涉及 **ephemeral-workspace-manager** 时，调用 `../pm-b07-ephemeral-workspace-manager/SKILL.md`。
- 当任务涉及 **dependency-proxy-and-cache** 时，调用 `../pm-b07-dependency-proxy-and-cache/SKILL.md`。
- 当任务涉及 **artifact-signing-and-provenance** 时，调用 `../pm-b07-artifact-signing-and-provenance/SKILL.md`。
- 当任务涉及 **reproducible-build-validator** 时，调用 `../pm-b07-reproducible-build-validator/SKILL.md`。
- 当任务涉及 **malicious-build-script-detector** 时，调用 `../pm-b07-malicious-build-script-detector/SKILL.md`。
- 当任务涉及 **execution-audit-recorder** 时，调用 `../pm-b07-execution-audit-recorder/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `untrusted-code-sandbox` | 在强隔离、非 root、受限系统调用和可销毁环境中执行不可信代码。 |
| `network-egress-policy` | 默认禁止外网，按域名、协议、时间和任务最小化开放依赖获取与测试出口。 |
| `resource-quota-governor` | 限制 CPU、内存、磁盘、进程、文件句柄、GPU、网络和执行时长。 |
| `secret-scope-manager` | 按任务注入最小必要凭证，阻止跨项目、跨租户和跨阶段访问。 |
| `ephemeral-workspace-manager` | 创建内容寻址、隔离、可快照和任务结束后可销毁的工作空间。 |
| `dependency-proxy-and-cache` | 通过受控代理、镜像和缓存获取依赖，并记录来源、摘要和许可证。 |
| `artifact-signing-and-provenance` | 为源码、规则、模型输出、构建产物和证据生成签名与来源链。 |
| `reproducible-build-validator` | 在独立环境重复构建并比较产物、元数据和非确定性来源。 |
| `malicious-build-script-detector` | 检测危险安装脚本、宿主访问、凭证读取、持久化、挖矿和供应链行为。 |
| `execution-audit-recorder` | 记录工具调用、命令、文件变化、网络、资源、凭证作用域和决策审计。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
