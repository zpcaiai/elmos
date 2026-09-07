---
name: elmos-multilanguage-parsing
description: 实现多语言 AST、符号、类型和语义抽取，生成统一 Code IR。用于任何代码导航、架构发现、流程或转换分析。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: analysis-core
  title_zh: 多语言解析与标准化 Code IR
  batch: BATCH-01-ingestion-and-parsing
  owner: elmos-project-intelligence
---

# 多语言解析与标准化 Code IR

## 目标

以可增量、可容错方式把支持语言标准化为统一符号与关系模型。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Project Revision
- technology fingerprint
- parser registry
- 编译配置

## 必须输出

- AST shards
- Code IR
- parse diagnostics
- unsupported constructs

## 执行流程

1. 为每种语言选择 Tree-sitter、编译器前端或 LSP 适配器。
2. 解析文件并保留位置、注释、语法节点和错误节点。
3. 解析包、模块、类型、函数、变量、注解、路由和配置绑定。
4. 标准化跨语言 Symbol ID 和 Type ID。
5. 关联生成代码、源映射、宏展开与 partial class。
6. 按文件内容哈希增量更新 IR。

## 实施要求

- 解析失败不得阻断整个项目。
- 保留 byte range、line/column 和 revision。
- 动态语言同时输出静态候选与置信度。
- 每个 parser 版本写入 analysis run。
- IR Schema 必须向后兼容或带迁移器。

## 安全与可信度约束

- 不得把解析错误节点当作已确认语义。
- 不得执行不可信构建脚本来获得 AST，除非在隔离沙箱且获授权。
- 跨语言统一不能丢失语言特有语义。

## 依赖技能

- `elmos-project-fingerprinting`

## 预期交付物

- `code-ir.jsonl`
- `parse-diagnostics.json`

## 完成定义

- [ ] 受支持基准仓库文件解析成功率达到设定阈值。
- [ ] 增量修改单文件只重建受影响 shard。
- [ ] Symbol 位置与在线代码阅读器行号一致。
- [ ] 不支持语法有明确诊断和降级输出。
- [ ] Code IR 通过 Schema 验证。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
