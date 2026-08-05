# Codex Implementation Prompt — Batch 01

你正在实现 `batch-01`：**Batch 1：竞争格局、产品定位与持续竞争情报**。

## 必读文件

开始编码前，完整阅读：

```text
README.md
SKILL.md
SKILL_INDEX.md
FOUNDATION_COMPATIBILITY.md
IMPLEMENTATION_CHECKLIST.md
VALIDATION_REPORT.md
schemas/
policies/
examples/
tests/SCENARIOS.md
skills/*/SKILL.md
```

不得只读取根 `SKILL.md` 后跳过子 Skill。

## 总目标

建立可重复、可审计、可持续更新的竞争情报与产品定位系统，为后续应用评估、迁移规划、代码转换、数据库迁移、验证、切换和商业化提供统一战略约束。

## 可信边界

- 官方文档、可重复测试和经核验客户证据优先于营销材料。
- Vendor Claim、独立验证、推断和未知必须分离。
- 产品定位只能引用当前有证据的能力；Roadmap 必须明确标记。
- 关键结论绑定 EvidenceRef、适用版本、工作负载和过期时间。

## 强制工程原则

- Evidence Before Scoring
- Capability Atomicity
- Direction-specific Route Analysis
- Workflow Continuity over Feature Count
- Trust Model over Marketing Correctness
- Cloud-neutral and Sovereignty-aware
- Cost per Verified Migrated Workload
- Unknown Must Remain Unknown

## 禁止事项

- 不直接修改客户代码或数据库。
- 不根据厂商营销材料宣称实际转换成功率。
- 不把功能存在等同于生产成熟。
- 不把一次性调研当作持续竞争情报。
- 不使用违法、泄密或违反服务条款的资料。
- 不以未经证实的攻击性比较支持销售。

## 建议仓库形态

```text
apps/
  api/
  console/
services/
packages/
  contracts/
  domain/
  adapters/
  policy/
  evidence/
  observability/
workers/
schemas/
policies/
tests/
  unit/
  contract/
  integration/
  security/
  certification/
```

可根据目标仓库技术栈调整目录，但不得破坏 Schema、证书、证据和兼容边界。

## 实现阶段

### Phase 1: 市场与证据基础

- 实现 Market Boundary、Competitor Registry、Evidence Graph 和 Claim 模型。
- 建立证据抓取适配器与合法合规策略。
- 实现实体解析、过期和冲突工作流。

### Phase 2: 统一能力与矩阵

- 实现 Capability Taxonomy 与 Normalizer。
- 实现生命周期、路线、数据库、Trust、Deployment、Economics 矩阵。
- 为所有矩阵建立 EvidenceRef。

### Phase 3: 基准、机会与定位

- 实现 Claim Benchmark 协议。
- 实现 Gap/Opportunity Engine。
- 实现 Positioning Decision、Product Boundary 和 Reference Route Gate。

### Phase 4: Battlecard 与持续监测

- 实现 Battlecard 生成和禁止话术。
- 实现 Release、Pricing、License、Acquisition 监测。
- 实现重新评分、证书失效和审计 Console。


## 每个阶段必须执行

1. 运行单元测试、契约测试和静态检查。
2. 更新实现清单，但不得篡改验证要求以制造通过。
3. 记录未实现范围、Unknown、风险与下一阶段依赖。
4. 对任何 Schema、策略或证书变化增加兼容性测试。
5. 对失败路径、暂停恢复、幂等、权限和失效规则编写测试。
6. 运行 `python tools/validate_package.py`，保持规格包本身有效。

## 输出要求

最终提交至少包含：

```text
可运行服务或库
数据库迁移脚本
OpenAPI 或等价 API 契约
事件和任务契约
测试与 Fixtures
本地启动说明
CI 配置
威胁模型与权限说明
观测指标
证书与证据样例
实现状态矩阵
```

## 完成标准

- 16 个 Skills 均有可运行实现或明确 experimental 状态。
- 关键结论可从 Evidence Graph 重算。
- 所有评分区分 unknown、partial、preview 和 verified。
- 产品定位、边界、Reference Route 和销售话术可审计。
- Batch 1 Certificate 可签发、失效和撤销。

任何未达到的项目必须标为 `not-implemented`、`partial` 或 `experimental`；禁止用文档宣称替代实现和测试。
