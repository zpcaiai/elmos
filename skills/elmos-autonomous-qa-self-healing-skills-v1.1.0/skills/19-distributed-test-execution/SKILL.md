---
id: 19-distributed-test-execution
name: Distributed Test Execution
version: 1.1.0
category: execution
depends_on:
  - 17-test-data-management
  - 18-environment-orchestration
---

# Distributed Test Execution

## 目标

对不同类型测试进行分片、并行、调度、限额、背压与容错，同时保持严格结果语义。

## 何时调用

当工作流进入 `19-distributed-test-execution` 对应阶段，或上游技能产物变化导致本阶段失效时调用。不得跳过依赖技能直接伪造输入。

## 输入契约

- 可执行 TestCase、环境和数据租约
- 资源/时间预算、优先级与依赖图
- Worker 能力和适配器注册表

## 输出契约

- 每个分片和测试的状态、attempt 与证据引用
- 资源使用、队列时间、关键路径和实时进度
- 可恢复 checkpoint 与未提交工作列表

## 执行步骤

1. 根据时长、资源、环境和依赖生成分片。
2. P0/P1、失败复现和关键路径优先调度。
3. 采用租约与 fencing token 防止旧 Worker 重复提交。
4. 实时采集日志、trace、metric 和 heartbeat。
5. Worker 失败只重放未提交分片，已提交结果保持不可变。
6. 执行完成后检查所有 Required 测试都有合法终态。

## 不可违反的控制

- 重试只能用于波动分类，首次失败证据必须保留。
- 分片重放不得重复不可逆副作用。
- 资源不足时要背压或失败，不得过载共享环境。
- SKIPPED 不能作为发布终态。

## 完成判定

- Worker/网络失败后任务可恢复。
- 结果 exactly-once 提交或通过幂等达到等效语义。
- 所有 Required 用例有终态和证据。
- 执行进度与 ETA 可实时查询。

## 失败处理

- 输入缺失或 Schema 不合法：标记 `BLOCKED`，保留诊断，不得猜测为成功。
- 可恢复基础设施失败：保存检查点并按受限策略重试。
- 产品或策略失败：生成结构化缺陷/门禁结果，不得通过跳过或弱化规则绕过。
- 所有失败均写入证据清单和审计事件。

## v1.1.0 执行来源

- Worker 只能执行 Manifest 中已物化、已校验的测试文件，不直接执行 Agent 返回的临时代码字符串。
- 每个分片记录 artifact refs、文件哈希和运行命令，恢复时校验内容未漂移。
