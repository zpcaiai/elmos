# Codex Implementation Prompt — Batch 02

你正在实现 `batch-02`：**Batch 2：应用现代化自动评估**。

## 必读文件

开始编码前，完整阅读：

```text
README.md
SKILL.md
SKILL_INDEX.md
BATCH01_COMPATIBILITY.md
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

对企业应用组合、源码、二进制、基础设施、运行环境、数据库、集成关系和业务约束进行自动化评估，建立可复现现状快照，生成证据化架构、风险、候选路线、区间预测、迁移波次和 Assessment Certificate。

## 可信边界

- Measured、Deterministic Analysis、Inferred 和 Unknown 分离。
- 所有分析绑定不可变 Snapshot、工具版本和 EvidenceRef。
- Sandbox Build 与 Probe 不连接生产资源。
- 证书范围不能超过真实资产覆盖与证据等级。

## 强制工程原则

- Snapshot First
- Evidence Before Inference
- Read-only by Default
- Static + Binary + Runtime + Documentation
- Build-aware Analysis
- Target-neutral Before Provider-specific
- Direction-specific Route Assessment
- Interval Prediction Instead of Point Promise
- Unknown Must Remain Unknown

## 禁止事项

- 不直接修改生产代码或数据库。
- 不执行未经授权的二进制反编译。
- 不把源码扫描成功等同于应用可迁移。
- 不把编译成功等同于行为等价。
- 不输出没有置信区间的精确工期或成本承诺。
- 不把云适配建议等同于生产上线批准。

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

### Phase 1: Intake、授权与 Snapshot

- 实现 Portfolio、Scope、Expected Asset Register。
- 实现 Access Grant、Data Handling 和 Snapshot Merkle Root。
- 完成 SCM、Artifact、Infrastructure、Runtime、Database 和 Document Connector 契约。

### Phase 2: Inventory 与分析图谱

- 实现 Canonical Workload Inventory 和 Entity Resolution。
- 实现 Semantic Index、Architecture、Dependency、Call、Dataflow 和 Runtime Correlation。
- 实现 Evidence Quality 与 Conflict。

### Phase 3: 风险与路线

- 实现 Technical Debt、Security/SBOM 和 Cloud Fit。
- 实现多策略 Directional Migration Candidate。
- 实现 Required Validation 和 Rollback Plan。

### Phase 4: Probe、预测、波次与证书

- 实现安全 Sandbox Probe。
- 实现 Quantile Prediction、Calibration 和 OOD。
- 实现 Wave Planner、Report、A0-A5 Certificate 和失效。


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

- 21 个 Skills 均有可运行实现或明确状态。
- Snapshot、资产分母、EvidenceRef 和 Coverage 可审计。
- 架构、依赖、数据流和运行基线可查询。
- 候选路线、预测和波次均有假设、区间和 Blocker。
- A0–A5 Certificate 可签发、失效、撤销和增量更新。

任何未达到的项目必须标为 `not-implemented`、`partial` 或 `experimental`；禁止用文档宣称替代实现和测试。
