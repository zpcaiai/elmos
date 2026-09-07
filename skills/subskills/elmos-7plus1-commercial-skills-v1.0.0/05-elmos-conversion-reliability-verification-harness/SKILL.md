---
name: elmos-conversion-reliability-verification-harness
description: 以 Requirement/Capability Ledger、机械化完成门、差分运行时、全栈测试、故障注入、自动修复和证据包证明项目生成与跨库转换正确且完整。
license: Proprietary
compatibility: Codex, Claude Code, OpenCode, DeepSeek Harness, OpenHarness and native Elmos runtimes through versioned adapters
metadata:
  package_id: P05
  version: 1.0.0
  phase: "Phase 1（P0 最高优先级）"
  dependencies: "00, 01, 02"
  maturity: commercial-product-blueprint
---

# Elmos 转换可靠性、验证与证据完成门

## 使命

直接决定 Elmos 是否能把“生成代码”变成“可证明完成的软件工程交付”，也是降低假完成率的核心。

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

**依赖：** P00, P01, P02

- 任何模型或 Agent 的自评只作为线索，不作为 pass 证据。
- 单一综合分数不能掩盖关键 Gate 失败、未知缺口或不适用测试。
- 自动修复不能修改验收标准来让测试通过。

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

- COMPLETED 状态只由 Gate Engine 写入，其他组件只能请求评估。
- 所有测试绑定 source revision、target revision、environment、seed 和 tool version。
- 验证器默认 read-only；修复由独立 Repair Agent 在范围化权限下执行。
- 差分比较先规范化非语义噪声，再比较业务可观察行为。
- 豁免必须有 owner、理由、风险、补偿控制、到期时间和人工审批。
- 证据可重放或至少可验证 hash/签名与来源。

## 可按需加载的子 Skills

| Skill | 职责 |
| --- | --- |
| `skills/requirement-coverage-ledger/SKILL.md` | 追踪每条需求从来源到设计、实现、测试和证据的闭环。 |
| `skills/capability-coverage-ledger/SKILL.md` | 追踪源能力到目标映射、实现、编译、测试和行为验证。 |
| `skills/mechanical-completion-gate/SKILL.md` | 用硬条件和证据判定是否完成，忽略 Agent 自评。 |
| `skills/verification-planner/SKILL.md` | 根据变更图、风险和栈生成最小充分验证 DAG。 |
| `skills/compiler-static-pipeline/SKILL.md` | 运行 build、lint、typecheck、static/security/architecture checks。 |
| `skills/contract-integration-pipeline/SKILL.md` | 验证 API、Schema、事件、DB、MQ、缓存、权限和外部集成。 |
| `skills/differential-runtime/SKILL.md` | 在相同输入下比较源与目标的可观察行为和副作用。 |
| `skills/generative-testing/SKILL.md` | 发现样例测试覆盖不到的边界和隐藏语义错误。 |
| `skills/ui-multimodal-verifier/SKILL.md` | 比较源目标 DOM、状态、视觉、视频、交互、无障碍和平台行为。 |
| `skills/nonfunctional-verifier/SKILL.md` | 验证商业项目的容量、延迟、安全、恢复和依赖可信性。 |
| `skills/diagnosis-repair-loop/SKILL.md` | 聚类失败、定位根因、范围化修复并持续回归，直到 Gate 或 blocker。 |
| `skills/evidence-certification-engine/SKILL.md` | 生成可审计、可签名、可交付的质量证据和生产认证。 |

## 必须产出

- P05 Package Manifest 与 immutable config revision
- 计划/Workpad/验收/风险/决策记录
- 本包领域输出、事件、指标和证据引用
- 兼容性、迁移与回滚记录
- P05 GateDecision 或明确 blocker

## 完成判定

- Requirement 与 Capability closure 达到策略阈值，Critical unknown gap=0。
- build/static/contract/differential/E2E/security 的 required gates 全部 pass。
- Critical/High mismatch、存活关键 mutation、未处理严重漏洞为 0。
- TODO/stub/mock/unsupported 均被计算并符合政策；不得隐藏。
- 证据 freshness、source/target revision、environment 与工具版本一致。
- 所有 waiver 未过期并有正式审批与补偿控制。

## 失败处理

| 失败模式 | 强制处置 |
| --- | --- |
| 测试波动 | 隔离 flake、重复运行统计、修复根因；关键 Gate 不允许简单 rerun-until-pass。 |
| 源系统无法启动 | 使用契约/Trace/recorded behavior 作为降级证据并降低认证等级。 |
| 环境差异导致假 mismatch | 环境指纹对齐、规范化时间/ID/顺序后再判定。 |
| Repair 反复破坏其他模块 | 扩大回归闭包、回滚尝试、触发 no-progress/human gate。 |
| 证据体量过大 | 内容寻址存储，Bundle 保留索引/hash/摘要并支持按需读取。 |

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
