---
name: batch-16-backend-direction-packs
description: 为六种后端语言的 30 条有方向路径分别维护源特性、目标特性、规则、依赖、变异、黄金仓库和验证策略。
---

# Batch 16：后端30条有方向转换包

## Goal

为六种后端语言的 30 条有方向路径分别维护源特性、目标特性、规则、依赖、变异、黄金仓库和验证策略。

## Position in the system

- Phase: `E 后端语言互转`
- Included skills: `30`
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

- 当任务涉及 **java-to-csharp-direction-pack** 时，调用 `skills/java-to-csharp-direction-pack/SKILL.md`。
- 当任务涉及 **java-to-go-direction-pack** 时，调用 `skills/java-to-go-direction-pack/SKILL.md`。
- 当任务涉及 **java-to-rust-direction-pack** 时，调用 `skills/java-to-rust-direction-pack/SKILL.md`。
- 当任务涉及 **java-to-python-direction-pack** 时，调用 `skills/java-to-python-direction-pack/SKILL.md`。
- 当任务涉及 **java-to-typescript-direction-pack** 时，调用 `skills/java-to-typescript-direction-pack/SKILL.md`。
- 当任务涉及 **csharp-to-java-direction-pack** 时，调用 `skills/csharp-to-java-direction-pack/SKILL.md`。
- 当任务涉及 **csharp-to-go-direction-pack** 时，调用 `skills/csharp-to-go-direction-pack/SKILL.md`。
- 当任务涉及 **csharp-to-rust-direction-pack** 时，调用 `skills/csharp-to-rust-direction-pack/SKILL.md`。
- 当任务涉及 **csharp-to-python-direction-pack** 时，调用 `skills/csharp-to-python-direction-pack/SKILL.md`。
- 当任务涉及 **csharp-to-typescript-direction-pack** 时，调用 `skills/csharp-to-typescript-direction-pack/SKILL.md`。
- 当任务涉及 **go-to-java-direction-pack** 时，调用 `skills/go-to-java-direction-pack/SKILL.md`。
- 当任务涉及 **go-to-csharp-direction-pack** 时，调用 `skills/go-to-csharp-direction-pack/SKILL.md`。
- 当任务涉及 **go-to-rust-direction-pack** 时，调用 `skills/go-to-rust-direction-pack/SKILL.md`。
- 当任务涉及 **go-to-python-direction-pack** 时，调用 `skills/go-to-python-direction-pack/SKILL.md`。
- 当任务涉及 **go-to-typescript-direction-pack** 时，调用 `skills/go-to-typescript-direction-pack/SKILL.md`。
- 当任务涉及 **rust-to-java-direction-pack** 时，调用 `skills/rust-to-java-direction-pack/SKILL.md`。
- 当任务涉及 **rust-to-csharp-direction-pack** 时，调用 `skills/rust-to-csharp-direction-pack/SKILL.md`。
- 当任务涉及 **rust-to-go-direction-pack** 时，调用 `skills/rust-to-go-direction-pack/SKILL.md`。
- 当任务涉及 **rust-to-python-direction-pack** 时，调用 `skills/rust-to-python-direction-pack/SKILL.md`。
- 当任务涉及 **rust-to-typescript-direction-pack** 时，调用 `skills/rust-to-typescript-direction-pack/SKILL.md`。
- 当任务涉及 **python-to-java-direction-pack** 时，调用 `skills/python-to-java-direction-pack/SKILL.md`。
- 当任务涉及 **python-to-csharp-direction-pack** 时，调用 `skills/python-to-csharp-direction-pack/SKILL.md`。
- 当任务涉及 **python-to-go-direction-pack** 时，调用 `skills/python-to-go-direction-pack/SKILL.md`。
- 当任务涉及 **python-to-rust-direction-pack** 时，调用 `skills/python-to-rust-direction-pack/SKILL.md`。
- 当任务涉及 **python-to-typescript-direction-pack** 时，调用 `skills/python-to-typescript-direction-pack/SKILL.md`。
- 当任务涉及 **typescript-to-java-direction-pack** 时，调用 `skills/typescript-to-java-direction-pack/SKILL.md`。
- 当任务涉及 **typescript-to-csharp-direction-pack** 时，调用 `skills/typescript-to-csharp-direction-pack/SKILL.md`。
- 当任务涉及 **typescript-to-go-direction-pack** 时，调用 `skills/typescript-to-go-direction-pack/SKILL.md`。
- 当任务涉及 **typescript-to-rust-direction-pack** 时，调用 `skills/typescript-to-rust-direction-pack/SKILL.md`。
- 当任务涉及 **typescript-to-python-direction-pack** 时，调用 `skills/typescript-to-python-direction-pack/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `java-to-csharp-direction-pack` | 提供从 Java 到 C# 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `java-to-go-direction-pack` | 提供从 Java 到 Go 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `java-to-rust-direction-pack` | 提供从 Java 到 Rust 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `java-to-python-direction-pack` | 提供从 Java 到 Python 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `java-to-typescript-direction-pack` | 提供从 Java 到 TypeScript/Node.js 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `csharp-to-java-direction-pack` | 提供从 C# 到 Java 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `csharp-to-go-direction-pack` | 提供从 C# 到 Go 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `csharp-to-rust-direction-pack` | 提供从 C# 到 Rust 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `csharp-to-python-direction-pack` | 提供从 C# 到 Python 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `csharp-to-typescript-direction-pack` | 提供从 C# 到 TypeScript/Node.js 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `go-to-java-direction-pack` | 提供从 Go 到 Java 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `go-to-csharp-direction-pack` | 提供从 Go 到 C# 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `go-to-rust-direction-pack` | 提供从 Go 到 Rust 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `go-to-python-direction-pack` | 提供从 Go 到 Python 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `go-to-typescript-direction-pack` | 提供从 Go 到 TypeScript/Node.js 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `rust-to-java-direction-pack` | 提供从 Rust 到 Java 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `rust-to-csharp-direction-pack` | 提供从 Rust 到 C# 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `rust-to-go-direction-pack` | 提供从 Rust 到 Go 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `rust-to-python-direction-pack` | 提供从 Rust 到 Python 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `rust-to-typescript-direction-pack` | 提供从 Rust 到 TypeScript/Node.js 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `python-to-java-direction-pack` | 提供从 Python 到 Java 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `python-to-csharp-direction-pack` | 提供从 Python 到 C# 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `python-to-go-direction-pack` | 提供从 Python 到 Go 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `python-to-rust-direction-pack` | 提供从 Python 到 Rust 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `python-to-typescript-direction-pack` | 提供从 Python 到 TypeScript/Node.js 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `typescript-to-java-direction-pack` | 提供从 TypeScript/Node.js 到 Java 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `typescript-to-csharp-direction-pack` | 提供从 TypeScript/Node.js 到 C# 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `typescript-to-go-direction-pack` | 提供从 TypeScript/Node.js 到 Go 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `typescript-to-rust-direction-pack` | 提供从 TypeScript/Node.js 到 Rust 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |
| `typescript-to-python-direction-pack` | 提供从 TypeScript/Node.js 到 Python 的仓库级专用转换与验证包，覆盖类型、错误、副作用、并发、框架、依赖和目标惯用实现。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
