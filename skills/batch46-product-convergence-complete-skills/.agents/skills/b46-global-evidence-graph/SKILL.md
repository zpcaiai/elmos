---
name: b46-global-evidence-graph
description: 连接Source、PSP/UIR、Rule、Patch、Test、Approval、Release、Production与Customer Acceptance。
---

# Skill 1503：全局Evidence Graph

## 适用场景

- 将《ELMOS项目整体缺口与产品级优化报告》中的结构性建议转化为生产代码、契约和可验证证据。
- 收敛Batch 1–45已有能力，避免继续平行建设重复内核。
- Codex需要修改真实仓库、生成ExecPlan、实现垂直切片并运行严格Gate时。

## 目标

连接Source、PSP/UIR、Rule、Patch、Test、Approval、Release、Production与Customer Acceptance。

## 前置依赖

- `1498`
- `1501`

## 必需输入

- 当前仓库`AGENTS.md`、架构决策、Batch 1–45能力和测试清单。
- 精确Source Commit、Target Commit、Release Digest和Environment Digest。
- 现有Pack、Workflow、Policy、Evidence、Runner、Certification及Owner清单。
- 当前能力支持矩阵、技术债、客户约束和严格测试结果。

## 强制不变量

- 每个节点和边有Tenant、Project、Stable ID、Digest、Producer、时间、版本、Trust、Retention和Signature。
- Owner不得使用`TBD`、`unknown`、`team`等占位值。
- 结论必须绑定精确Artifact、环境、Policy、工具链和Evidence Digest。
- 不得删除失败测试、自动更新Golden、扩大Tolerance或手改认证状态。
- 任何跨Tenant访问、数据丢失、Policy绕过、Runner逃逸或Evidence篡改立即停止。

## 预期仓库落点

- `services/control-plane/evidence/`
- `contracts/evidence/`
- `db/migrations/evidence_graph/`

## 实施流程

1. **盘点**：搜索现有实现、契约、数据表、API、状态机、脚本和Skill，标记权威实现、重复实现和缺口。
2. **冻结契约**：先创建或升级JSON Schema、API/Event Contract和版本策略，再修改业务代码。
3. **设计最小切片**：选择能够跨越真实输入、处理、持久化、验证和Evidence的最小生产形态路径。
4. **实现确定性内核**：优先使用类型化模型、规则和受控状态机；Agent只处理经过Policy允许的长尾。
5. **兼容迁移**：为旧Batch能力提供Adapter、Migration和弃用计划，禁止长期双内核。
6. **安全与隔离**：实现Tenant、Project、Data Classification、Residency、Least Privilege和审计边界。
7. **失败与恢复**：增加超时、重试、幂等、Checkpoint、补偿、Rollback、断连和升级中断测试。
8. **真实验证**：运行真实编译器、数据库、Runner、Browser、Cloud Sandbox或客户环境；不可用时保持blocked。
9. **更新全局事实**：写入Capability Registry、Dependency Graph、Evidence Graph、Lifecycle和Convergence Dashboard。
10. **认证**：执行相关Batch严格测试、Batch 46 Complete测试和最终Gate，证据不足时不得升级状态。

## 必需输出

- 生产实现或明确的Blocker，不得只输出设计文档。
- 版本化Schema、API/Event Contract、Migration和Rollback。
- 正常、边界、负向、安全、故障、升级、重放和Evidence篡改测试。
- 原始运行日志、Artifact/Environment Digest、Replay命令和Evidence Manifest。
- ADR、支持矩阵、Known Limitation、Owner和维护计划。

## 验证

```bash
python3 scripts/batch46-complete/validate_skill_bundle.py .
python3 scripts/batch46-complete/validate_convergence_pack.py convergence-packs/reference-product
python3 scripts/batch46-complete/run_convergence_gate.py convergence-packs/reference-product
python3 -m unittest tests/batch46-complete/test_toolkit.py
```

## 负向测试要求

- 缺失Owner、占位Digest、未知依赖和循环依赖必须失败。
- 平行Workflow/Policy/Evidence内核未经批准必须失败。
- 只有文档、Mock或目标输出自证时不得通过。
- 少于两家独立Design Partner、无真实Private Runner或无Handoff时最终认证必须失败。

## 停止与升级

- 出现P0未知语义、跨租户、数据丢失、Secret泄漏、未授权Egress、重复副作用或客户业务回归。
- 实现需要复制已有权威Kernel，且不能证明隔离、性能或迁移必要性。
- 真实工具链或客户环境不可用，无法取得该能力强制要求的证据。

## 完成定义

- 代码、契约、测试、迁移、回滚、Owner和不可变Evidence完整。
- 通过对应严格测试，Critical Unknown与零容忍Finding为0。
- 与Batch 1–45兼容且不存在未治理的平行内核。
- 独立工程师可以从Evidence和Replay命令重现结论。
