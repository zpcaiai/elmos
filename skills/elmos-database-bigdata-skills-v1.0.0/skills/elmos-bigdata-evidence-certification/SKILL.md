---
name: elmos-bigdata-evidence-certification
description: 按 E1–E5 证据等级验证功能、数据、性能、安全、恢复、成本和运维准备度。
version: 1.0.0
group: bigdata-core
dependencies: ["elmos-data-architecture-adr", "elmos-bigdata-security-governance", "elmos-bigdata-test-validation", "elmos-bigdata-performance-chaos", "elmos-bigdata-cost-autotuning", "elmos-bigdata-auto-repair"]
triggers: ["准备交付或上线", "生产认证", "可信完成度报告"]
outputs: ["evidence-bundle/", "readiness-scorecard.json", "production-certificate.md", "handoff/"]
---

# 大数据项目证据包与生产认证

## 目标

按 E1–E5 证据等级验证功能、数据、性能、安全、恢复、成本和运维准备度。

## 适用触发条件

- 准备交付或上线
- 生产认证
- 可信完成度报告

## 输入

- 需求/ADR
- 代码部署
- 测试/性能/安全/恢复
- runbook/owner

## 执行流程

1. **CERT-001** — E1 静态完整性：文件、schema、依赖、配置、文档和追踪矩阵。
2. **CERT-002** — E2 本地/组件：单元、契约、质量和关键组件运行。
3. **CERT-003** — E3 集成/E2E：真实 connector、数据流、API、BI、权限。
4. **CERT-004** — E4 生产相似：压力、混沌、恢复、升级、成本、多租户。
5. **CERT-005** — E5 受控生产/影子：真实 SLO、告警、回滚、运营闭环。
6. **CERT-006** — 每项结论记录 evidence URI、环境、版本、时间、范围；区分 implemented/configured/tested/verified/certified。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `evidence-bundle/`
- `readiness-scorecard.json`
- `production-certificate.md`
- `handoff/`

## 验收标准

- 认证级别与证据一致。
- 未通过门禁有阻断/条件。
- 生产声明不靠静态文件。
- 证据可离线审计。

## 失败、降级与恢复

证据不足时只颁发实际可达等级，绝不自动写“生产就绪”。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **CERT-007** — 输入和授权范围已固化为不可变快照。
- [ ] **CERT-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **CERT-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **CERT-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **CERT-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **CERT-012** — 未验证能力未被标记为生产完成。
