---
id: 05-test-model-dsl
name: Unified Test Model & DSL
version: 1.1.0
category: generation
depends_on:
  - 04-risk-coverage-planning
---

# Unified Test Model & DSL

## 目标

用统一版本化 DSL 表达跨语言、跨框架的测试，使规划、生成、执行、证据和报告解耦。

## 何时调用

当工作流进入 `05-test-model-dsl` 对应阶段，或上游技能产物变化导致本阶段失效时调用。不得跳过依赖技能直接伪造输入。

## 输入契约

- TestPlan 与追踪图
- 语言/框架适配器能力
- 环境、数据和 Oracle 策略

## 输出契约

- 符合 test-case.schema.json 的 ExecutableTestCase
- 参数化场景、步骤、Oracle、清理和证据声明
- DSL 版本、生成器版本和可重放命令

## 执行步骤

1. 定义 TestCase、Step、Oracle、Fixture、Environment、Evidence 和 Cleanup。
2. 为状态机、角色、负载、故障注入和 UI 交互提供扩展字段。
3. 实现 Schema 校验、规范化序列化和内容哈希。
4. 将 DSL 编译为语言/工具专用测试或直接执行计划。
5. 对生成结果做静态可执行性检查，拒绝空断言和未绑定变量。
6. 保存 DSL 与生成产物映射，便于重新生成和差分。

## 不可违反的控制

- DSL 必须是数据，不允许嵌入未审计的任意代码。
- 所有外部副作用步骤必须声明幂等和清理策略。
- Oracle 不得为空或仅检查进程成功。
- 版本升级必须有迁移器和兼容性测试。

## 完成判定

- 同一 DSL 在相同适配器版本下生成稳定产物。
- 非法或不完整用例在执行前被拒绝。
- 至少支持单元/API/UI/性能/安全/混沌类型。
- 每个生成文件可回链到 DSL 和需求。

## 失败处理

- 输入缺失或 Schema 不合法：标记 `BLOCKED`，保留诊断，不得猜测为成功。
- 可恢复基础设施失败：保存检查点并按受限策略重试。
- 产品或策略失败：生成结构化缺陷/门禁结果，不得通过跳过或弱化规则绕过。
- 所有失败均写入证据清单和审计事件。

## 项目产出要求（v1.1.0）

- 本技能产生或修改的测试源、配置、数据、基线、报告、补丁或证据必须登记到 `ProjectOutputManifest`。
- 测试相关文件必须通过 `37-test-source-materialization` 写入目标生态原生目录；只存在于临时上下文不算完成。
- 任何文件变化都要更新 SHA-256、需求/用例引用和谱系；未登记文件不得进入最终 Bundle。
