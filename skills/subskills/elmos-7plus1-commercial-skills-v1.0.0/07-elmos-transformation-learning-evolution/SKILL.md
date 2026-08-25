---
name: elmos-transformation-learning-evolution
description: 把每次经过验证的生成、转换、失败、修复、规则、项目模式和证据沉淀为可复用知识，并通过严格晋升、基准回归和专项模型训练持续提高质量。
license: Proprietary
compatibility: Codex, Claude Code, OpenCode, DeepSeek Harness, OpenHarness and native Elmos runtimes through versioned adapters
metadata:
  package_id: P07
  version: 1.0.0
  phase: "Phase 3（长期复利护城河）"
  dependencies: "00, 02, 03, 05, 06"
  maturity: commercial-product-blueprint
---

# Elmos 转换知识沉淀、自学习与能力进化

## 使命

形成属于 Elmos 自己的 Software Transformation Intelligence，使模型和 Harness 可替换，而转换能力随项目数量复利增长。

## 何时调用

- 用户或上游任务明确需要本包的能力范围。
- 本包依赖的输入或合同发生版本变化，需要重新构建、验证或迁移。
- P05、生产监控、上游 breaking change 或客户验收发现本包相关缺口。
- 不应调用本包来绕过其他包的边界；详见“禁止事项”。

## 必需输入

- 目标仓库或项目生成需求，以及不可变 source revision / request revision。
- 租户、项目、隐私、预算、时间、允许的模型/Provider/工具和审批策略。
- 上游 Package 输出与其 Schema 版本；缺少依赖时必须阻断。
- 选定 Phase、目标 maturity（prototype/internal-beta/commercial-ga）和认证等级。

## 依赖与边界

**依赖：** P00, P02, P03, P05, P06

- 任何未经 P05 验证的输出不得进入 trusted/certified 知识。
- 租户私有代码/规则默认不进入全局知识；只允许授权、脱敏和抽象后的资产。
- 学习系统不能在无回归证据时自动修改生产规则。

## 执行工作流

1. 读取本包 `PRODUCT-CAPABILITY-SPEC.md`、`ARCHITECTURE.md` 与 `ACCEPTANCE-GATES.md`，确认范围和硬不变量。
2. 执行 `readiness`：检查依赖包、Schema、源版本、权限、沙箱、模型、工具、预算和环境。
3. 创建或更新本包 Workpad：计划、验收、验证、风险、假设、阻塞与证据索引。
4. 按 `PHASE-PLAN.md` 和 `IMPLEMENTATION-BACKLOG.md` 选择最小可交付工作流，不跨越未通过的 Phase Gate。
5. 执行子 Skills；所有输出使用 `schemas/` 与根目录共享 Schema 校验，并写入版本化事件/台账。
6. 运行 `BENCHMARKS-AND-EVALS.md` 中与变更相关的定向测试和影响闭包回归。
7. 把结果送入 P05 Evidence Gate；失败则进入诊断/修复，禁止用文本声明替代证据。
8. 通过后生成 handoff：变更、证据、残余风险、成本、系统 ETA、回滚和兼容性。

## 硬不变量

- 知识条目始终绑定 provenance、tenant/IP scope、版本、验证证据和 maturity。
- 一次修复成功最多进入 EXPERIMENTAL/CANDIDATE，不可直接 trusted。
- 规则晋升必须通过跨项目回归与负向测试；失败自动降级/隔离。
- 全局知识不保存可重构租户专有代码的原文或敏感数据。
- Benchmark 数据集版本固定、任务泄漏受控、评测结果可复现。
- 专项模型输出仍受 P03 规则与 P05 Gate 约束。

## 可按需加载的子 Skills

| Skill | 职责 |
| --- | --- |
| `skills/transformation-knowledge-base/SKILL.md` | 沉淀可复用的语言、框架、API、类型、事务、并发、异常、安全、数据与消息转换知识。 |
| `skills/project-archetype-knowledge-base/SKILL.md` | 沉淀完整商业项目的能力基线、架构模式、周边功能和验收模板。 |
| `skills/failure-repair-corpus/SKILL.md` | 保存从错误到根因、修复和验证的完整轨迹。 |
| `skills/rule-promotion-governance/SKILL.md` | 管理 EXPERIMENTAL→CANDIDATE→VALIDATED→TRUSTED→CERTIFIED→DEPRECATED。 |
| `skills/benchmark-corpus/SKILL.md` | 维护可复现的项目生成、跨语言、框架现代化和前端转换基准。 |
| `skills/evidence-corpus/SKILL.md` | 保存编译、测试、差分、生产、回滚等签名验证结果，为学习提供可信标签。 |
| `skills/repair-retrieval-ranker/SKILL.md` | 根据失败签名、上下文和适用条件选择历史修复候选。 |
| `skills/drift-regression-detector/SKILL.md` | 检测模型、Harness、规则、框架和依赖变化引起的质量退化。 |
| `skills/active-learning-queue/SKILL.md` | 优先处理最能提升覆盖率和减少未知 gap 的样本。 |
| `skills/specialized-model-training/SKILL.md` | 训练 Semantic Mapper、Gap Detector、Rule Selector、Repair Ranker、Verification Planner 等小模型。 |
| `skills/tenant-ip-isolation/SKILL.md` | 管理私有、组织和全局知识的范围、同意、脱敏、保留与删除。 |
| `skills/knowledge-quality-auditor/SKILL.md` | 检查重复、冲突、过期、毒化、证据缺失、覆盖盲区和异常推广。 |

## 必须产出

- P07 Package Manifest 与 immutable config revision
- 计划/Workpad/验收/风险/决策记录
- 本包领域输出、事件、指标和证据引用
- 兼容性、迁移与回滚记录
- P05 GateDecision 或明确 blocker

## 完成判定

- trusted/certified 知识均有跨项目证据、适用条件、负向测试和 owner。
- Release benchmark 无未接受 Critical regression。
- Repair/Rule 检索严格遵守租户/IP scope。
- 专项模型 shadow 达到质量/成本/安全阈值后才可 canary。
- 知识冲突、过期规则和撤销证据能够自动降级并触发回归。

## 失败处理

| 失败模式 | 强制处置 |
| --- | --- |
| 错误经验污染 | 隔离 candidate、撤销证据、降级规则、重跑受影响 corpus。 |
| 知识过拟合某项目 | 增加跨项目/负向验证与 applicability predicate。 |
| 框架版本漂移 | 按版本分支规则、标记 stale、触发兼容 benchmark。 |
| 租户数据误入全局 | 立即 quarantine、审计传播路径、删除派生数据并通知治理流程。 |
| 专项模型退化 | 停止 canary、回退 deterministic/通用模型、保存失败样本。 |

## 禁止事项

- 禁止把“模型说已完成”“代码看起来合理”“大部分测试通过”作为完成证据。
- 禁止静默忽略 unsupported capability、低置信结论、失败 Hook、partial sandbox 或过期证据。
- 禁止跨租户复用代码、Prompt、Trace、规则或修复案例，除非有明确 scope 与授权。
- 禁止直接跟随上游 main/dev/preview；必须使用 Pin、Adapter 和 conformance tests。
- 禁止降低验收标准来修复失败；应修改实现、扩大证据或明确 blocker/waiver。

## 参考文件

- `README.md`
- `PRODUCT-CAPABILITY-SPEC.md`
- `ARCHITECTURE.md`
- `PHASE-PLAN.md`
- `INTERFACE-CONTRACTS.md`
- `DATA-AND-EVENT-MODEL.md`
- `SECURITY-AND-GOVERNANCE.md`
- `OBSERVABILITY-AND-SLO.md`
- `BENCHMARKS-AND-EVALS.md`
- `ACCEPTANCE-GATES.md`
- `FAILURE-MODES-AND-RECOVERY.md`
- `IMPLEMENTATION-BACKLOG.md`
