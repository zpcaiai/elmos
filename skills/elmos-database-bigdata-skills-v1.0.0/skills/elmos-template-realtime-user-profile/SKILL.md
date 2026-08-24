---
name: elmos-template-realtime-user-profile
description: 生成多源身份合并、实时标签、历史画像、特征服务、低延迟 serving 和隐私治理。
version: 1.0.0
group: bigdata-templates
dependencies: ["elmos-bigdata-project-orchestrator", "elmos-feature-store-ml-pipeline"]
triggers: ["实时用户画像", "Customer 360", "营销分群/个性化"]
outputs: ["template-plan.json", "generated-project/"]
---

# 实时用户画像与 Customer 360 模板

## 目标

生成多源身份合并、实时标签、历史画像、特征服务、低延迟 serving 和隐私治理。

## 适用触发条件

- 实时用户画像
- Customer 360
- 营销分群/个性化

## 输入

- 身份标识
- 事件与业务数据
- 标签特征
- 隐私同意

## 执行流程

1. **TPL360-001** — 设计 identity graph、主身份、设备合并、冲突和可撤销关联。
2. **TPL360-002** — 生成 CDC/事件采集、实时标签、离线历史回填和画像版本。
3. **TPL360-003** — 用权威历史层+低延迟 serving store 组合，明确缓存和重建。
4. **TPL360-004** — 定义标签、freshness、TTL、置信度和 owner。
5. **TPL360-005** — 实现 consent、purpose、删除传播、masking 和跨租户隔离。
6. **TPL360-006** — 验证误合并、迟到、重复、删除、实时/离线一致和查询延迟。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `template-plan.json`
- `generated-project/`

## 验收标准

- 身份规则可解释可回滚。
- 标签有版本/freshness/owner。
- 删除/同意变化可传播。
- 实时历史可对账。

## 失败、降级与恢复

身份置信度不足时保持多候选或匿名，不强制合并。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **TPL360-007** — 输入和授权范围已固化为不可变快照。
- [ ] **TPL360-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **TPL360-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **TPL360-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **TPL360-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **TPL360-012** — 未验证能力未被标记为生产完成。
