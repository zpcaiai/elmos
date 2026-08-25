---
id: 28-quality-gate-release-certification
name: Quality Gate & Release Certification
version: 1.1.0
category: certification
depends_on:
  - 26-impact-analysis-regression
---

# Quality Gate & Release Certification

## 目标

以版本化、可解释规则评估覆盖、执行、缺陷、性能、UI、安全和修复结果，生成可独立验证的发布证书。

## 何时调用

当工作流进入 `28-quality-gate-release-certification` 对应阶段，或上游技能产物变化导致本阶段失效时调用。不得跳过依赖技能直接伪造输入。

## 输入契约

- QUALITY_GATES、TraceabilityGraph、TestRun
- 缺陷、补丁、性能/UI/安全结果和证据 manifest
- 审批、例外、输入快照和候选提交

## 输出契约

- 逐规则 GateResult、失败原因和责任项
- ReleaseCertificate、签名与哈希
- 允许发布、等待审批或拒绝发布结论

## 执行步骤

1. 冻结候选提交、需求快照、门禁版本和证据清单。
2. 逐条执行覆盖、状态、缺陷、性能、UI、安全和修复规则。
3. 验证例外权限、范围、补偿、到期和审批链。
4. 检查报告和证据完整性、哈希及重放命令。
5. 生成机器可读与人可读门禁结果。
6. 签发证书或明确拒绝，禁止模糊“基本通过”。

## 不可违反的控制

- 门禁规则不得被 Fixer 修改。
- Required 测试 BLOCKED/FLAKY/FAILED 均不可认证。
- Critical/High 缺陷和安全发现默认为零容忍。
- 证书只对应一个不可变快照与提交。

## 完成判定

- 每个门禁结论可追溯到事实对象。
- 证书可离线验证哈希和签名。
- 例外可查询责任人和到期日。
- 输入变化会使旧证书失效。

## 失败处理

- 输入缺失或 Schema 不合法：标记 `BLOCKED`，保留诊断，不得猜测为成功。
- 可恢复基础设施失败：保存检查点并按受限策略重试。
- 产品或策略失败：生成结构化缺陷/门禁结果，不得通过跳过或弱化规则绕过。
- 所有失败均写入证据清单和审计事件。

## 项目产出要求（v1.1.0）

- 本技能产生或修改的测试源、配置、数据、基线、报告、补丁或证据必须登记到 `ProjectOutputManifest`。
- 测试相关文件必须通过 `37-test-source-materialization` 写入目标生态原生目录；只存在于临时上下文不算完成。
- 任何文件变化都要更新 SHA-256、需求/用例引用和谱系；未登记文件不得进入最终 Bundle。
