---
name: pm-b44-enterprise-private-commercialization
description: "支持企业内网、完全离线、多租户、SSO、审计、授权、白标、SLA 和客户私有规则包的商业交付. Precision Migration B44 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Batch 44：企业私有化与商业交付
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b44-enterprise-private-commercialization`.
- Immutable source identity: `batch-44-enterprise-private-commercialization` in `precision-migration-b01-44` (B44).
- Runtime adapter: `enterprise-private-commercialization`; binding state: `DECLARED`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b44-enterprise-private-commercialization`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Goal

支持企业内网、完全离线、多租户、SSO、审计、授权、白标、SLA 和客户私有规则包的商业交付。

## Position in the system

- Phase: `L 证据、上线和产品化`
- Included skills: `12`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 汇总证据与未解决项
2. 执行硬性发布门禁
3. 影子/Canary/渐进切换
4. 监控并自动回滚
5. 沉淀反例、规则和企业交付能力

## Shared gates

- 未解决阻断项必须为0
- 生产副作用必须可抑制、可回滚或经批准
- 证据、环境和产物必须可追踪与签名

## Dispatch rules

- 当任务涉及 **private-deployment-planner** 时，调用 `../pm-b44-private-deployment-planner/SKILL.md`。
- 当任务涉及 **air-gapped-installation** 时，调用 `../pm-b44-air-gapped-installation/SKILL.md`。
- 当任务涉及 **offline-toolchain-registry** 时，调用 `../pm-b44-offline-toolchain-registry/SKILL.md`。
- 当任务涉及 **private-model-gateway** 时，调用 `../pm-b44-private-model-gateway/SKILL.md`。
- 当任务涉及 **multi-tenant-isolation** 时，调用 `../pm-b44-multi-tenant-isolation/SKILL.md`。
- 当任务涉及 **rbac-and-sso** 时，调用 `../pm-b44-rbac-and-sso/SKILL.md`。
- 当任务涉及 **audit-and-compliance** 时，调用 `../pm-b44-audit-and-compliance/SKILL.md`。
- 当任务涉及 **license-and-entitlement** 时，调用 `../pm-b44-license-and-entitlement/SKILL.md`。
- 当任务涉及 **white-label-partner-mode** 时，调用 `../pm-b44-white-label-partner-mode/SKILL.md`。
- 当任务涉及 **enterprise-reporting** 时，调用 `../pm-b44-enterprise-reporting/SKILL.md`。
- 当任务涉及 **sla-and-support-readiness** 时，调用 `../pm-b44-sla-and-support-readiness/SKILL.md`。
- 当任务涉及 **customer-private-rule-pack** 时，调用 `../pm-b44-customer-private-rule-pack/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `private-deployment-planner` | 根据网络、数据、模型、工具链、规模和合规规划私有部署拓扑。 |
| `air-gapped-installation` | 打包离线镜像、依赖、工具链、模型、许可证、升级和验证流程。 |
| `offline-toolchain-registry` | 维护离线可验证的编译器、Runtime、数据库、浏览器、设备和证明工具。 |
| `private-model-gateway` | 接入客户自有、开源或国产模型，支持审计、限流、路由和版本锁定。 |
| `multi-tenant-isolation` | 实现租户、仓库、工作区、数据、模型、缓存、密钥和证据隔离。 |
| `rbac-and-sso` | 实现组织、角色、项目、审批、SSO、SCIM 和最小权限。 |
| `audit-and-compliance` | 记录不可抵赖操作、数据处理、模型调用、审批和证据保留。 |
| `license-and-entitlement` | 管理版本、方向包、席位、并发、容量、离线授权和许可证合规。 |
| `white-label-partner-mode` | 为集成商和厂商提供品牌、租户、报告、规则和交付流程定制。 |
| `enterprise-reporting` | 生成技术、管理、审计、合规、成本、SLA 和项目组合报告。 |
| `sla-and-support-readiness` | 定义监控、值班、升级、响应、恢复、版本支持和客户沟通机制。 |
| `customer-private-rule-pack` | 安全开发、测试、签名、部署和升级客户私有转换规则与知识。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
