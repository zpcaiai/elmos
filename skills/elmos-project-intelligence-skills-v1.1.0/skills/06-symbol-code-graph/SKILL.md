---
name: elmos-symbol-code-graph
description: 构建定义、引用、继承、实现、调用、读写和跨语言边。用于语义导航、调用链、影响分析和架构抽取。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: analysis-core
  title_zh: 符号、引用与调用图
  batch: BATCH-02-graphs-and-evidence
  owner: elmos-project-intelligence
---

# 符号、引用与调用图

## 目标

把离散 Code IR 连接为可查询、可增量更新的 Code Graph。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Code IR
- 构建依赖
- 路由/API Schema
- 语言解析诊断

## 必须输出

- symbol graph
- call graph
- type hierarchy
- unresolved edge report

## 执行流程

1. 创建文件、模块、包、类型、函数和字段节点。
2. 解析定义/引用、继承/实现、调用者/被调用者。
3. 识别依赖注入、反射注册、路由绑定和 ORM 映射。
4. 构建前端页面到 API、API 到服务、服务到数据库的跨层边。
5. 为边保存解析策略、证据和置信度。
6. 计算 SCC、中心性、扇入扇出和循环依赖。

## 实施要求

- 支持静态精确边、静态候选边和运行时确认边并存。
- Graph ID 稳定，跨增量 run 可复用。
- 查询必须支持 revision 和 branch 隔离。
- 边删除必须基于新 revision 正确回收。
- 高基数关系支持分页和采样。

## 安全与可信度约束

- 不得把字符串相似性匹配标记为 Confirmed。
- 运行时边不能覆盖静态候选历史。
- 跨租户节点和查询必须隔离。

## 依赖技能

- `elmos-multilanguage-parsing`

## 预期交付物

- `code-graph-snapshot.json`
- `unresolved-edges.json`

## 完成定义

- [ ] Go to definition、find references 和 call hierarchy 在基准项目通过。
- [ ] 循环依赖检测与人工基线一致。
- [ ] 每条边可返回 evidence 与解析方法。
- [ ] 增量更新后无幽灵边。
- [ ] 图查询 p95 达到 SLO。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
