---
name: elmos-template-recommendation-system
description: 生成行为采集、候选/排序特征、训练集、召回索引、在线特征、实验和监控。
version: 1.0.0
group: bigdata-templates
dependencies: ["elmos-bigdata-project-orchestrator", "elmos-feature-store-ml-pipeline"]
triggers: ["个性化推荐", "内容/商品排序", "召回与在线特征"]
outputs: ["template-plan.json", "generated-project/"]
---

# 推荐系统数据与在线服务模板

## 目标

生成行为采集、候选/排序特征、训练集、召回索引、在线特征、实验和监控。

## 适用触发条件

- 个性化推荐
- 内容/商品排序
- 召回与在线特征

## 输入

- 行为和物品
- 标签目标
- 在线延迟
- 实验反馈

## 执行流程

1. **TPLREC-001** — 生成曝光、点击、停留、转化和负样本事件契约。
2. **TPLREC-002** — 建立 point-in-time training set、特征和标签延迟窗口。
3. **TPLREC-003** — 设计批/流特征、online store、候选索引、缓存和模型服务边界。
4. **TPLREC-004** — 生成召回、粗排、精排、规则和冷启动数据路径。
5. **TPLREC-005** — 实现 A/B、探索、反馈回流、偏差、漂移和异常监控。
6. **TPLREC-006** — 验证训练泄漏、特征一致、延迟、降级和结果可追踪。

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

- 训练无未来泄漏。
- 在线/离线特征一致。
- 曝光反馈闭环完整。
- 有热门/规则降级。

## 失败、降级与恢复

缺少可靠曝光日志时不得把点击率直接当无偏效果。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **TPLREC-007** — 输入和授权范围已固化为不可变快照。
- [ ] **TPLREC-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **TPLREC-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **TPLREC-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **TPLREC-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **TPLREC-012** — 未验证能力未被标记为生产完成。
