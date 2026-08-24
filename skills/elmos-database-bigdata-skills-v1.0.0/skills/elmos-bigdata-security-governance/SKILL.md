---
name: elmos-bigdata-security-governance
description: 跨湖、仓、流、消息、目录、BI 和 ML 实施分类、授权、脱敏、保留、审计和数据治理。
version: 1.0.0
group: bigdata-core
dependencies: ["elmos-database-security-multitenancy", "elmos-metadata-catalog-lineage", "elmos-bigdata-infra-deployment"]
triggers: ["企业大数据平台", "敏感/受监管数据", "数据产品治理"]
outputs: ["governance/", "classification-policy.json", "retention-policy.json", "access-review.md"]
---

# 大数据安全、治理、生命周期与合规

## 目标

跨湖、仓、流、消息、目录、BI 和 ML 实施分类、授权、脱敏、保留、审计和数据治理。

## 适用触发条件

- 企业大数据平台
- 敏感/受监管数据
- 数据产品治理

## 输入

- 数据分类
- Lineage/Catalog
- 身份租户
- 法规政策

## 执行流程

1. **GOV-001** — 建立组织级数据分类与自动标签，覆盖 source/topic/bucket/table/column/feature/dashboard/export。
2. **GOV-002** — 实施 RBAC/ABAC、purpose-based access、row/column policy、masking、tokenization。
3. **GOV-003** — 定义 consent、retention、legal hold、right-to-delete、归档和可验证删除传播。
4. **GOV-004** — 设计跨区域/跨云/跨域驻留、传输、egress 和审批。
5. **GOV-005** — 记录访问、变更、导出、模型使用、策略决策和管理员行为。
6. **GOV-006** — 建立 owner/steward、数据产品 SLA、认证/弃用/例外/复审和政策即代码测试。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `governance/`
- `classification-policy.json`
- `retention-policy.json`
- `access-review.md`

## 验收标准

- 策略覆盖复制和派生数据。
- 删除/保留/授权沿 lineage 传播。
- 权限复审并检测漂移。
- 合规结论绑定证据范围。

## 失败、降级与恢复

法规映射未验证时标记需合规确认，技术上先采用更严格最小权限。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **GOV-007** — 输入和授权范围已固化为不可变快照。
- [ ] **GOV-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **GOV-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **GOV-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **GOV-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **GOV-012** — 未验证能力未被标记为生产完成。
