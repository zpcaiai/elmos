---
name: elmos-data-architecture-lineage
description: 分析数据库、ORM、SQL、缓存、搜索、文件、消息和数据转换，生成 ER 图、数据流图、CRUD 矩阵、敏感数据流和数据血缘。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: architecture
  title_zh: 数据架构、ER、DFD 与血缘
  batch: BATCH-04-architecture-flow-data
  owner: elmos-project-intelligence
---

# 数据架构、ER、DFD 与血缘

## 目标

建立数据资产、字段、读写、转换、生命周期和功能之间的可追踪模型。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- DDL/migrations
- ORM/SQL
- API/Event schema
- Code Graph
- 运行查询/Trace（可选）

## 必须输出

- Data IR
- ERD
- DFD
- lineage graph
- CRUD matrix
- sensitive-data map

## 执行流程

1. 抽取数据库、Schema、表、字段、索引、约束和实体。
2. 解析 ORM、手写 SQL、Repository 和迁移历史。
3. 识别 API/事件字段到内部模型和持久化字段映射。
4. 识别缓存、搜索索引、对象存储和 ETL 流。
5. 标注敏感等级、保留期限、加密和跨境边界。
6. 生成 ER、DFD、血缘、生命周期、CRUD 与数据质量视图。

## 实施要求

- 字段级血缘区分 Confirmed、Mapped、Inferred。
- 支持多数据库、多租户、分库分表和读写分离。
- Schema 版本与代码 revision 对齐。
- 数据流图包含信任边界、外部系统和存储。
- 导出 Mermaid/PlantUML/Graphviz/CSV/JSON。

## 安全与可信度约束

- 不得读取真实生产数据内容来推断 Schema，除非明确授权并脱敏。
- 字段名称相似不能作为唯一血缘证据。
- 敏感数据图必须执行更严格权限。

## 依赖技能

- `elmos-project-intelligence-graph`

## 预期交付物

- `data-ir.json`
- `erd.json`
- `data-lineage.json`
- `crud-matrix.csv`

## 完成定义

- [ ] ER 图与迁移/ORM 核心关系一致。
- [ ] 主要写路径能追到数据资产。
- [ ] CRUD 矩阵无跨 revision 混合。
- [ ] 敏感字段分类有证据和人工复核入口。
- [ ] 血缘边可回溯转换表达式或代码位置。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
