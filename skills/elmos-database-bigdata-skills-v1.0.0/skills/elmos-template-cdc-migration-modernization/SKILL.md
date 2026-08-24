---
name: elmos-template-cdc-migration-modernization
description: 生成全量+增量复制、影子验证、湖仓/新库落地、渐进切流和回滚完整迁移工程。
version: 1.0.0
group: bigdata-templates
dependencies: ["elmos-bigdata-project-orchestrator", "elmos-database-migration-modernization"]
triggers: ["旧数仓/数据库迁移", "实时复制", "Hadoop/遗留 ETL 现代化"]
outputs: ["template-plan.json", "generated-project/"]
---

# CDC 迁移、实时复制与旧数据平台现代化模板

## 目标

生成全量+增量复制、影子验证、湖仓/新库落地、渐进切流和回滚完整迁移工程。

## 适用触发条件

- 旧数仓/数据库迁移
- 实时复制
- Hadoop/遗留 ETL 现代化

## 输入

- 源目标
- 历史与日志
- 停机一致性
- 应用报表依赖

## 执行流程

1. **TPLMIG-001** — 生成源盘点、DDL/SQL/作业/报表依赖和差异矩阵。
2. **TPLMIG-002** — 生成 snapshot、CDC、offset、水位、重放、断点和幂等。
3. **TPLMIG-003** — 建立旧新双运行、影子查询、行数/校验和/业务不变量/性能对比。
4. **TPLMIG-004** — 按表/域/租户/流量渐进切换并设置自动回滚阈值。
5. **TPLMIG-005** — 保留历史回填、schema 演进、删除传播和下游重建。
6. **TPLMIG-006** — 生成退役、归档、审计、成本和生产认证证据。

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

- 全量增量无缺口。
- 旧新行为性能有差分。
- 切流可回滚。
- 迁移可断点恢复。

## 失败、降级与恢复

不可转换语义隔离为定制适配任务，不静默丢失。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **TPLMIG-007** — 输入和授权范围已固化为不可变快照。
- [ ] **TPLMIG-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **TPLMIG-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **TPLMIG-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **TPLMIG-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **TPLMIG-012** — 未验证能力未被标记为生产完成。
