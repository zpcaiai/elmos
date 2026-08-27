# Rewrite Recipe Layer

这里的 recipe 是 Elmos 确定性转换层的实现契约，不允许在没有 Semantic IR 前置条件时直接运行。

## 三段式

```text
Applicability
  - source evidence
  - semantic IR pattern
  - target baseline
  - policy

Rewrite
  - AST/symbol/config operations
  - generated support code
  - dependency/build changes

Postconditions
  - parse/type resolution
  - no incompatible javax
  - route/security/binding invariants
  - source map entry
  - selected tests
```

## 原则

- recipe 必须幂等。
- recipe 的每个修改点产生 `changeOperationId`。
- XML/配置改写采用结构模型，保留有语义的顺序。
- 模型生成的局部 patch 作为 `ConstrainedSemanticPatch`，不是 recipe 的隐式步骤。
- recipe 失败不允许退回 regex-only。
- 与 Spring Boot 4 版本相关的 API 必须从 target adapter/version catalog 解析。
