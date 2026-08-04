# Codex Implementation Prompt — Batch 04

你正在实现 `batch-04`：**Batch 4：跨语言语义映射、Transformation Rule DSL 与 Deterministic Recipe Engine**。

## 必读文件

开始编码前，完整阅读：

```text
README.md
SKILL.md
SKILL_INDEX.md
BATCH03_COMPATIBILITY.md
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

构建以 CSIR 为语义可信底座、以确定性 Recipe Runtime 为执行可信根、以原生 Codemod/Compiler Pass 为语言适配器、以受限 Agent 为最后修复层的统一软件转换内核。

## 可信边界

- 确定性 Rule Compiler 与 Runtime 是执行可信根。
- 原生 OpenRewrite、Codemod、Compiler Pass 通过 Adapter 进入统一 Patch/Journal/Evidence。
- Agent 只在确定性转换之后、最小范围内提出 Patch。
- 所有修改发生在 Copy-on-write Workspace，并由独立 Verification 决定提交。

## 强制工程原则

- Directional Semantic Mapping
- Deterministic First
- Plan and Explain Before Apply
- Explicit Read/Write and Analysis Contracts
- Stable Anchors, Not Line Numbers
- Atomic Cross-domain Patch
- No Last-write-wins
- Independent Verification
- Agent Bounded and Last
- Every Change Is Reversible and Traceable

## 禁止事项

- 不在本 Batch 完成所有目标语言最终 Printer。
- 不承诺任意语言之间自动无损转换。
- 不允许 Agent 直接写客户主分支或自行批准输出。
- 不允许规则绕过编译、测试或验证门禁。
- 不把 AST 形状相似视为语义等价。
- 不允许未经签名 Recipe 获得高权限。
- 不自动执行生产数据库数据迁移。

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

### Phase 1: Mapping、DSL 与 Compiler

- 实现 Directional Semantic Mapping Registry。
- 实现 Rule DSL、Schema、Linter、Type Checker 和 Static Safety。
- 实现 CompiledRuleIR、Digest 与 Permission Manifest。

### Phase 2: Matcher、Planner 与 Runtime

- 实现 Semantic Matcher、Tri-state Guard 和 Patch Planner。
- 实现 Recipe DAG、Analysis Contract 和 Deterministic Runtime。
- 实现稳定并行、Cycle 和 Explain Plan。

### Phase 3: Adapters、跨域 Patch 与事务

- 实现 OpenRewrite、Codemod 和 Compiler Pass Adapter。
- 实现 Cross-file/Build/Config/API/SQL Rewriter。
- 实现 Conflict Engine、COW Workspace、Journal、Rollback 和 Provenance。

### Phase 4: Verification、Agent、Registry 与认证

- 实现 V0–V9 Verification。
- 实现 Restricted Agent 和 Rule Distillation。
- 实现 Package Registry、Corpus Benchmark、RC0–RC6 与 Run Certificate。


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

- 25 个 Skills 均有可运行实现或明确状态。
- 相同输入和环境产生稳定 Match、Plan 和 Patch Digest。
- OpenRewrite、Codemod 和 Compiler Pass 进入统一事务与证据链。
- Agent 修改范围受限、独立验证且完整披露。
- Recipe、Route Pack 和 Transformation Run 可认证、失效和撤销。

任何未达到的项目必须标为 `not-implemented`、`partial` 或 `experimental`；禁止用文档宣称替代实现和测试。
