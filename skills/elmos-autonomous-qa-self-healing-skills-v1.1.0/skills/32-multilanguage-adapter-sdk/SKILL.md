---
id: 32-multilanguage-adapter-sdk
name: Multi-Language Adapter SDK
version: 1.1.0
category: platform
depends_on:
  - 05-test-model-dsl
---

# Multi-Language Adapter SDK

## 目标

为 Elmos 支持的语言和框架提供统一探测、生成、执行、覆盖率、诊断和修复接口。

## 何时调用

当工作流进入 `32-multilanguage-adapter-sdk` 对应阶段，或上游技能产物变化导致本阶段失效时调用。不得跳过依赖技能直接伪造输入。

## 输入契约

- 统一 Test DSL、ProjectSnapshot 和工具链映射
- 语言/框架构建、测试、覆盖率和静态分析命令
- 沙箱、环境与证据接口

## 输出契约

- Adapter 插件、能力声明和版本
- 生成产物、执行命令、结果解析和诊断
- 适配器契约测试与兼容性矩阵

## 执行步骤

1. 定义 detect/generate/validate/execute/collect_coverage/diagnose/apply_patch 接口。
2. 实现 Java、Kotlin、Python、C#、Go、Rust、C++、PHP、TS/JS、React、ObjC、Swift、Flutter 适配器。
3. 每个适配器声明支持的测试类型和工具能力。
4. 规范化 JUnit/coverage/log/trace 等结果到统一模型。
5. 使用金丝雀仓库执行适配器契约和错误注入测试。
6. 适配器升级保留版本和产物哈希。

## 不可违反的控制

- 适配器不得绕过沙箱或自行访问生产。
- 命令参数使用结构化数组，禁止不受控 shell 拼接。
- 不支持能力要明确返回 Unsupported，而非伪成功。
- 工具输出解析失败视为 BLOCKED/infra failure。

## 完成判定

- 每个声明支持语言通过契约测试。
- 相同 DSL 可生成对应框架可运行测试。
- 结果归一化字段完整。
- 适配器崩溃不影响控制面恢复。

## 失败处理

- 输入缺失或 Schema 不合法：标记 `BLOCKED`，保留诊断，不得猜测为成功。
- 可恢复基础设施失败：保存检查点并按受限策略重试。
- 产品或策略失败：生成结构化缺陷/门禁结果，不得通过跳过或弱化规则绕过。
- 所有失败均写入证据清单和审计事件。

## 项目产出要求（v1.1.0）

- 本技能产生或修改的测试源、配置、数据、基线、报告、补丁或证据必须登记到 `ProjectOutputManifest`。
- 测试相关文件必须通过 `37-test-source-materialization` 写入目标生态原生目录；只存在于临时上下文不算完成。
- 任何文件变化都要更新 SHA-256、需求/用例引用和谱系；未登记文件不得进入最终 Bundle。
