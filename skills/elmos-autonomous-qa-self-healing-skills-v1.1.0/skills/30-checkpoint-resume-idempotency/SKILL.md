---
id: 30-checkpoint-resume-idempotency
name: Checkpoint, Resume & Idempotency
version: 1.1.0
category: reliability
depends_on:
  - 00-qa-control-plane
  - 19-distributed-test-execution
---

# Checkpoint, Resume & Idempotency

## 目标

保证客户端断线、Worker 崩溃、编排服务重启和临时依赖失败后，测试与修复可继续而不重复危险副作用。

## 何时调用

当工作流进入 `30-checkpoint-resume-idempotency` 对应阶段，或上游技能产物变化导致本阶段失效时调用。不得跳过依赖技能直接伪造输入。

## 输入契约

- 工作流状态、事件日志、分片提交和环境租约
- 幂等键、fencing token、补偿规则和预算
- 缺陷、修复迭代、补丁和证据 manifest

## 输出契约

- 一致检查点、恢复计划和重放记录
- 已提交/未提交工作、孤儿租约和补偿结果
- 恢复后的同一 run_id 与连续事件序列

## 执行步骤

1. 在阶段边界和每个分片提交后写原子检查点。
2. 外部副作用携带 idempotency_key 和 causation_id。
3. Worker 使用租约与 fencing token，过期 Worker 无权提交。
4. 重启后从事件日志重建状态，再从最后检查点继续。
5. 客户端重新连接只 attach，不创建新任务。
6. 预算、修复尝试和证据引用一并恢复。

## 不可违反的控制

- 不得靠内存状态作为唯一事实源。
- 重放前必须判断副作用是否已提交。
- 恢复不能重置预算或修复次数。
- 取消与恢复并发时必须有确定优先级。

## 完成判定

- 杀死任一 Worker 后未完成分片可重跑且无重复副作用。
- 编排服务重启后任务继续。
- 客户端断线不影响服务端执行。
- 事件序列、检查点和最终报告一致。

## 失败处理

- 输入缺失或 Schema 不合法：标记 `BLOCKED`，保留诊断，不得猜测为成功。
- 可恢复基础设施失败：保存检查点并按受限策略重试。
- 产品或策略失败：生成结构化缺陷/门禁结果，不得通过跳过或弱化规则绕过。
- 所有失败均写入证据清单和审计事件。

## 项目产出要求（v1.1.0）

- 本技能产生或修改的测试源、配置、数据、基线、报告、补丁或证据必须登记到 `ProjectOutputManifest`。
- 测试相关文件必须通过 `37-test-source-materialization` 写入目标生态原生目录；只存在于临时上下文不算完成。
- 任何文件变化都要更新 SHA-256、需求/用例引用和谱系；未登记文件不得进入最终 Bundle。
