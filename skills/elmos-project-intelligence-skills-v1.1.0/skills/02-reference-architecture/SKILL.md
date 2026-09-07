---
name: elmos-reference-architecture
description: 设计或评审 Elmos Project Intelligence Studio 的生产级参考架构。用于服务拆分、数据存储、异步工作流、接口边界和技术选型。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: foundation
  title_zh: 参考架构与服务边界
  batch: BATCH-00-product-and-reference-architecture
  owner: elmos-project-intelligence
---

# 参考架构与服务边界

## 目标

建立可扩展、可替换、可私有化部署的参考架构，避免 UI、分析引擎、模型和存储相互耦合。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- 产品需求
- Elmos 现有架构
- 目标吞吐与仓库规模
- 部署环境

## 必须输出

- C4 架构
- 服务目录
- 数据存储分工
- 同步/异步接口
- ADR 与权衡

## 执行流程

1. 定义 Browser、Control Plane、Analysis Plane、Artifact Plane 和 Storage Plane。
2. 划分前端、项目 API、解析索引、图谱、AI 编排、渲染、导出和工作流服务。
3. 定义 PostgreSQL、图数据库、对象存储、搜索、缓存的职责和替换接口。
4. 定义 Temporal 工作流、事件总线和幂等键。
5. 定义多租户、网络边界、Secrets Broker 和审计。
6. 生成当前/目标架构图和 ADR。

## 实施要求

- 默认 UI 为 Vue 3 + TypeScript + Monaco；解析核心优先 Rust/Tree-sitter；AI 编排可用 Python/LangGraph；企业接口可用 Java/Spring。
- 模型、图存储、搜索、渲染器必须通过 Adapter/Port 可替换。
- 长任务状态不能只保存在进程内。
- 所有 artifact 绑定 project revision、analysis run 和 generator version。
- 运行时 Trace 与静态图谱分开采集、统一关联。

## 安全与可信度约束

- 不得让浏览器直接访问仓库密钥或对象存储主凭证。
- 不得把图数据库作为唯一事实源；原始证据必须可重建。
- 不得引入无明确职责的共享大服务。

## 依赖技能

- `elmos-product-scope`

## 预期交付物

- `docs/02-reference-architecture.md`
- `docs/adr/`
- `diagrams/reference-architecture.yaml`

## 完成定义

- [ ] 服务边界无循环部署依赖。
- [ ] 每个持久化数据类型有唯一主责存储。
- [ ] 任何 worker 重启后工作流可恢复。
- [ ] 架构支持 SaaS、单租户私有化和离线受限部署。
- [ ] ADR 记录关键替代方案及弃用原因。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
