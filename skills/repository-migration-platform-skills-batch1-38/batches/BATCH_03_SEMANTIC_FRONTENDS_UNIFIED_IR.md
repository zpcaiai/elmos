# Batch 03：10-Language Semantic Frontend与Unified Semantic IR

## Goal

为十种语言建立语义前端，统一类型、控制流、错误、副作用、并发、资源、协议与Source Map。

## Inputs

- Batch 1快照；
- 语言/编译器版本；
- Build graph；
- Runtime traces；

## Outputs

- AST/CST与symbol tables；
- Unified Semantic IR；
- Call/effect/data-flow graphs；
- Source maps；
- Unsupported semantics registry；

## Execution Flow

1. 调用官方编译器/解析器；
2. 恢复符号、类型与调用关系；
3. 结合Runtime补充动态事实；
4. Lower到Unified Semantic IR；
5. 执行前端Golden/Hidden/Fuzz验证；

## Verification

- 十语言Frontend可独立运行；
- 关键符号Source Map完整；
- 动态语义有置信度；
- Unsupported不静默丢弃；

## Stop Conditions

- 解析错误覆盖关键模块；
- 类型/符号恢复置信度不足；
- 生成代码或宏无法还原；

## Gate

`B03 Semantic Frontend Gate`

## Installable Skill

`agent-skills/runtime/b03-semantic-frontends-unified-ir/SKILL.md`
