---
name: batch-14-backend-compiler-adapters
description: 为 Java、C#、Go、Rust、Python 和 TypeScript/Node.js 提供原生语义前端、代码生成和测试工具链适配。
---

# Batch 14：后端语言Compiler Adapter

## Goal

为 Java、C#、Go、Rust、Python 和 TypeScript/Node.js 提供原生语义前端、代码生成和测试工具链适配。

## Position in the system

- Phase: `E 后端语言互转`
- Included skills: `60`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 使用语言原生前端恢复语义
2. Lower到Typed/Effect/State IR
3. 应用方向专用规则和依赖映射
4. 生成目标惯用代码
5. 构建、测试、双运行并按反例修复

## Shared gates

- 错误路径、事务和副作用必须保持
- 并发/取消/资源语义不得靠编译通过替代验证
- Direction Pack外的语义必须阻断或升级

## Dispatch rules

- 当任务涉及 **java-parser-adapter** 时，调用 `skills/java-parser-adapter/SKILL.md`。
- 当任务涉及 **java-symbol-adapter** 时，调用 `skills/java-symbol-adapter/SKILL.md`。
- 当任务涉及 **java-type-adapter** 时，调用 `skills/java-type-adapter/SKILL.md`。
- 当任务涉及 **java-cfg-ssa-adapter** 时，调用 `skills/java-cfg-ssa-adapter/SKILL.md`。
- 当任务涉及 **java-error-exception-adapter** 时，调用 `skills/java-error-exception-adapter/SKILL.md`。
- 当任务涉及 **java-async-concurrency-adapter** 时，调用 `skills/java-async-concurrency-adapter/SKILL.md`。
- 当任务涉及 **java-framework-detector** 时，调用 `skills/java-framework-detector/SKILL.md`。
- 当任务涉及 **java-code-generator** 时，调用 `skills/java-code-generator/SKILL.md`。
- 当任务涉及 **java-formatter-linter-adapter** 时，调用 `skills/java-formatter-linter-adapter/SKILL.md`。
- 当任务涉及 **java-test-adapter** 时，调用 `skills/java-test-adapter/SKILL.md`。
- 当任务涉及 **csharp-parser-adapter** 时，调用 `skills/csharp-parser-adapter/SKILL.md`。
- 当任务涉及 **csharp-symbol-adapter** 时，调用 `skills/csharp-symbol-adapter/SKILL.md`。
- 当任务涉及 **csharp-type-adapter** 时，调用 `skills/csharp-type-adapter/SKILL.md`。
- 当任务涉及 **csharp-cfg-ssa-adapter** 时，调用 `skills/csharp-cfg-ssa-adapter/SKILL.md`。
- 当任务涉及 **csharp-error-exception-adapter** 时，调用 `skills/csharp-error-exception-adapter/SKILL.md`。
- 当任务涉及 **csharp-async-concurrency-adapter** 时，调用 `skills/csharp-async-concurrency-adapter/SKILL.md`。
- 当任务涉及 **csharp-framework-detector** 时，调用 `skills/csharp-framework-detector/SKILL.md`。
- 当任务涉及 **csharp-code-generator** 时，调用 `skills/csharp-code-generator/SKILL.md`。
- 当任务涉及 **csharp-formatter-linter-adapter** 时，调用 `skills/csharp-formatter-linter-adapter/SKILL.md`。
- 当任务涉及 **csharp-test-adapter** 时，调用 `skills/csharp-test-adapter/SKILL.md`。
- 当任务涉及 **go-parser-adapter** 时，调用 `skills/go-parser-adapter/SKILL.md`。
- 当任务涉及 **go-symbol-adapter** 时，调用 `skills/go-symbol-adapter/SKILL.md`。
- 当任务涉及 **go-type-adapter** 时，调用 `skills/go-type-adapter/SKILL.md`。
- 当任务涉及 **go-cfg-ssa-adapter** 时，调用 `skills/go-cfg-ssa-adapter/SKILL.md`。
- 当任务涉及 **go-error-exception-adapter** 时，调用 `skills/go-error-exception-adapter/SKILL.md`。
- 当任务涉及 **go-async-concurrency-adapter** 时，调用 `skills/go-async-concurrency-adapter/SKILL.md`。
- 当任务涉及 **go-framework-detector** 时，调用 `skills/go-framework-detector/SKILL.md`。
- 当任务涉及 **go-code-generator** 时，调用 `skills/go-code-generator/SKILL.md`。
- 当任务涉及 **go-formatter-linter-adapter** 时，调用 `skills/go-formatter-linter-adapter/SKILL.md`。
- 当任务涉及 **go-test-adapter** 时，调用 `skills/go-test-adapter/SKILL.md`。
- 当任务涉及 **rust-parser-adapter** 时，调用 `skills/rust-parser-adapter/SKILL.md`。
- 当任务涉及 **rust-symbol-adapter** 时，调用 `skills/rust-symbol-adapter/SKILL.md`。
- 当任务涉及 **rust-type-adapter** 时，调用 `skills/rust-type-adapter/SKILL.md`。
- 当任务涉及 **rust-cfg-ssa-adapter** 时，调用 `skills/rust-cfg-ssa-adapter/SKILL.md`。
- 当任务涉及 **rust-error-exception-adapter** 时，调用 `skills/rust-error-exception-adapter/SKILL.md`。
- 当任务涉及 **rust-async-concurrency-adapter** 时，调用 `skills/rust-async-concurrency-adapter/SKILL.md`。
- 当任务涉及 **rust-framework-detector** 时，调用 `skills/rust-framework-detector/SKILL.md`。
- 当任务涉及 **rust-code-generator** 时，调用 `skills/rust-code-generator/SKILL.md`。
- 当任务涉及 **rust-formatter-linter-adapter** 时，调用 `skills/rust-formatter-linter-adapter/SKILL.md`。
- 当任务涉及 **rust-test-adapter** 时，调用 `skills/rust-test-adapter/SKILL.md`。
- 当任务涉及 **python-parser-adapter** 时，调用 `skills/python-parser-adapter/SKILL.md`。
- 当任务涉及 **python-symbol-adapter** 时，调用 `skills/python-symbol-adapter/SKILL.md`。
- 当任务涉及 **python-type-adapter** 时，调用 `skills/python-type-adapter/SKILL.md`。
- 当任务涉及 **python-cfg-ssa-adapter** 时，调用 `skills/python-cfg-ssa-adapter/SKILL.md`。
- 当任务涉及 **python-error-exception-adapter** 时，调用 `skills/python-error-exception-adapter/SKILL.md`。
- 当任务涉及 **python-async-concurrency-adapter** 时，调用 `skills/python-async-concurrency-adapter/SKILL.md`。
- 当任务涉及 **python-framework-detector** 时，调用 `skills/python-framework-detector/SKILL.md`。
- 当任务涉及 **python-code-generator** 时，调用 `skills/python-code-generator/SKILL.md`。
- 当任务涉及 **python-formatter-linter-adapter** 时，调用 `skills/python-formatter-linter-adapter/SKILL.md`。
- 当任务涉及 **python-test-adapter** 时，调用 `skills/python-test-adapter/SKILL.md`。
- 当任务涉及 **typescript-parser-adapter** 时，调用 `skills/typescript-parser-adapter/SKILL.md`。
- 当任务涉及 **typescript-symbol-adapter** 时，调用 `skills/typescript-symbol-adapter/SKILL.md`。
- 当任务涉及 **typescript-type-adapter** 时，调用 `skills/typescript-type-adapter/SKILL.md`。
- 当任务涉及 **typescript-cfg-ssa-adapter** 时，调用 `skills/typescript-cfg-ssa-adapter/SKILL.md`。
- 当任务涉及 **typescript-error-exception-adapter** 时，调用 `skills/typescript-error-exception-adapter/SKILL.md`。
- 当任务涉及 **typescript-async-concurrency-adapter** 时，调用 `skills/typescript-async-concurrency-adapter/SKILL.md`。
- 当任务涉及 **typescript-framework-detector** 时，调用 `skills/typescript-framework-detector/SKILL.md`。
- 当任务涉及 **typescript-code-generator** 时，调用 `skills/typescript-code-generator/SKILL.md`。
- 当任务涉及 **typescript-formatter-linter-adapter** 时，调用 `skills/typescript-formatter-linter-adapter/SKILL.md`。
- 当任务涉及 **typescript-test-adapter** 时，调用 `skills/typescript-test-adapter/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `java-parser-adapter` | 使用 Java 原生或高保真解析前端构建语法树，并保留源码位置、注释和语法特征。 |
| `java-symbol-adapter` | 解析 Java 符号、作用域、绑定、重载与跨文件引用，输出统一符号模型。 |
| `java-type-adapter` | 提取并规范化 Java 类型、泛型、可空性、联合类型和类型约束。 |
| `java-cfg-ssa-adapter` | 为 Java 构建控制流、数据流与 SSA/近似 SSA 表示，支持切片和验证。 |
| `java-error-exception-adapter` | 恢复 Java 的异常、错误返回、panic/throw 与清理路径语义。 |
| `java-async-concurrency-adapter` | 恢复 Java 的异步、线程、任务、协程、取消和同步原语语义。 |
| `java-framework-detector` | 识别 Java 仓库中的主流框架、版本、约定、插件和隐式运行时行为。 |
| `java-code-generator` | 从目标语义 IR 生成可构建、符合 Java 惯例且可追踪到源位置的代码。 |
| `java-formatter-linter-adapter` | 接入 Java 格式化、Lint 和静态分析工具，并规范化诊断结果。 |
| `java-test-adapter` | 发现、迁移、运行并规范化 Java 单元、集成、契约和端到端测试。 |
| `csharp-parser-adapter` | 使用 C# 原生或高保真解析前端构建语法树，并保留源码位置、注释和语法特征。 |
| `csharp-symbol-adapter` | 解析 C# 符号、作用域、绑定、重载与跨文件引用，输出统一符号模型。 |
| `csharp-type-adapter` | 提取并规范化 C# 类型、泛型、可空性、联合类型和类型约束。 |
| `csharp-cfg-ssa-adapter` | 为 C# 构建控制流、数据流与 SSA/近似 SSA 表示，支持切片和验证。 |
| `csharp-error-exception-adapter` | 恢复 C# 的异常、错误返回、panic/throw 与清理路径语义。 |
| `csharp-async-concurrency-adapter` | 恢复 C# 的异步、线程、任务、协程、取消和同步原语语义。 |
| `csharp-framework-detector` | 识别 C# 仓库中的主流框架、版本、约定、插件和隐式运行时行为。 |
| `csharp-code-generator` | 从目标语义 IR 生成可构建、符合 C# 惯例且可追踪到源位置的代码。 |
| `csharp-formatter-linter-adapter` | 接入 C# 格式化、Lint 和静态分析工具，并规范化诊断结果。 |
| `csharp-test-adapter` | 发现、迁移、运行并规范化 C# 单元、集成、契约和端到端测试。 |
| `go-parser-adapter` | 使用 Go 原生或高保真解析前端构建语法树，并保留源码位置、注释和语法特征。 |
| `go-symbol-adapter` | 解析 Go 符号、作用域、绑定、重载与跨文件引用，输出统一符号模型。 |
| `go-type-adapter` | 提取并规范化 Go 类型、泛型、可空性、联合类型和类型约束。 |
| `go-cfg-ssa-adapter` | 为 Go 构建控制流、数据流与 SSA/近似 SSA 表示，支持切片和验证。 |
| `go-error-exception-adapter` | 恢复 Go 的异常、错误返回、panic/throw 与清理路径语义。 |
| `go-async-concurrency-adapter` | 恢复 Go 的异步、线程、任务、协程、取消和同步原语语义。 |
| `go-framework-detector` | 识别 Go 仓库中的主流框架、版本、约定、插件和隐式运行时行为。 |
| `go-code-generator` | 从目标语义 IR 生成可构建、符合 Go 惯例且可追踪到源位置的代码。 |
| `go-formatter-linter-adapter` | 接入 Go 格式化、Lint 和静态分析工具，并规范化诊断结果。 |
| `go-test-adapter` | 发现、迁移、运行并规范化 Go 单元、集成、契约和端到端测试。 |
| `rust-parser-adapter` | 使用 Rust 原生或高保真解析前端构建语法树，并保留源码位置、注释和语法特征。 |
| `rust-symbol-adapter` | 解析 Rust 符号、作用域、绑定、重载与跨文件引用，输出统一符号模型。 |
| `rust-type-adapter` | 提取并规范化 Rust 类型、泛型、可空性、联合类型和类型约束。 |
| `rust-cfg-ssa-adapter` | 为 Rust 构建控制流、数据流与 SSA/近似 SSA 表示，支持切片和验证。 |
| `rust-error-exception-adapter` | 恢复 Rust 的异常、错误返回、panic/throw 与清理路径语义。 |
| `rust-async-concurrency-adapter` | 恢复 Rust 的异步、线程、任务、协程、取消和同步原语语义。 |
| `rust-framework-detector` | 识别 Rust 仓库中的主流框架、版本、约定、插件和隐式运行时行为。 |
| `rust-code-generator` | 从目标语义 IR 生成可构建、符合 Rust 惯例且可追踪到源位置的代码。 |
| `rust-formatter-linter-adapter` | 接入 Rust 格式化、Lint 和静态分析工具，并规范化诊断结果。 |
| `rust-test-adapter` | 发现、迁移、运行并规范化 Rust 单元、集成、契约和端到端测试。 |
| `python-parser-adapter` | 使用 Python 原生或高保真解析前端构建语法树，并保留源码位置、注释和语法特征。 |
| `python-symbol-adapter` | 解析 Python 符号、作用域、绑定、重载与跨文件引用，输出统一符号模型。 |
| `python-type-adapter` | 提取并规范化 Python 类型、泛型、可空性、联合类型和类型约束。 |
| `python-cfg-ssa-adapter` | 为 Python 构建控制流、数据流与 SSA/近似 SSA 表示，支持切片和验证。 |
| `python-error-exception-adapter` | 恢复 Python 的异常、错误返回、panic/throw 与清理路径语义。 |
| `python-async-concurrency-adapter` | 恢复 Python 的异步、线程、任务、协程、取消和同步原语语义。 |
| `python-framework-detector` | 识别 Python 仓库中的主流框架、版本、约定、插件和隐式运行时行为。 |
| `python-code-generator` | 从目标语义 IR 生成可构建、符合 Python 惯例且可追踪到源位置的代码。 |
| `python-formatter-linter-adapter` | 接入 Python 格式化、Lint 和静态分析工具，并规范化诊断结果。 |
| `python-test-adapter` | 发现、迁移、运行并规范化 Python 单元、集成、契约和端到端测试。 |
| `typescript-parser-adapter` | 使用 TypeScript/Node.js 原生或高保真解析前端构建语法树，并保留源码位置、注释和语法特征。 |
| `typescript-symbol-adapter` | 解析 TypeScript/Node.js 符号、作用域、绑定、重载与跨文件引用，输出统一符号模型。 |
| `typescript-type-adapter` | 提取并规范化 TypeScript/Node.js 类型、泛型、可空性、联合类型和类型约束。 |
| `typescript-cfg-ssa-adapter` | 为 TypeScript/Node.js 构建控制流、数据流与 SSA/近似 SSA 表示，支持切片和验证。 |
| `typescript-error-exception-adapter` | 恢复 TypeScript/Node.js 的异常、错误返回、panic/throw 与清理路径语义。 |
| `typescript-async-concurrency-adapter` | 恢复 TypeScript/Node.js 的异步、线程、任务、协程、取消和同步原语语义。 |
| `typescript-framework-detector` | 识别 TypeScript/Node.js 仓库中的主流框架、版本、约定、插件和隐式运行时行为。 |
| `typescript-code-generator` | 从目标语义 IR 生成可构建、符合 TypeScript/Node.js 惯例且可追踪到源位置的代码。 |
| `typescript-formatter-linter-adapter` | 接入 TypeScript/Node.js 格式化、Lint 和静态分析工具，并规范化诊断结果。 |
| `typescript-test-adapter` | 发现、迁移、运行并规范化 TypeScript/Node.js 单元、集成、契约和端到端测试。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
