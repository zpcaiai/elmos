---
name: elmos-conversion-integration
description: 把 Project Intelligence Studio 与整项目生成、多语言转换、Spring 翻新、Semantic IR、规则、自动修复、双运行和认证流程连接。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: integration
  title_zh: 与 Elmos 生成、转换、翻新引擎集成
  batch: BATCH-11-testing-conversion-estimation
  owner: elmos-project-intelligence
---

# 与 Elmos 生成、转换、翻新引擎集成

## 目标

形成导入—理解—转换—审阅—验证—文档/PPT—交付的统一闭环。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- source/target revisions
- conversion task
- Semantic IR
- rules/repairs/tests

## 必须输出

- source-target mapping
- conversion dashboards
- comparison artifacts
- certification evidence

## 执行流程

1. 让 Elmos 生成/转换中的中间 revision 直接进入阅读器。
2. 连接 Source Symbol、Semantic IR、Target Symbol 和 Rule 命中。
3. 生成模块、API、数据、流程和架构前后映射。
4. 显示未支持、低置信度、编译/测试失败和自动修复历史。
5. 将人工修改提炼为候选规则但不自动发布。
6. 完成后生成迁移文档、图表、PPT 和证据包。

## 实施要求

- 支持 Java、Kotlin、Python、C#、Go、Rust、C++、PHP、TypeScript/React、Objective-C、Swift、Flutter、JavaScript 目标矩阵。
- Source/Target/IR/Evidence 三至四栏可联动。
- 转换任务共享缓存、检查点、成本与 ETA。
- 功能保持、行为等价、性能等价分别建证据。
- Strangler、双运行和回滚状态可视化。

## 安全与可信度约束

- 不得把编译通过当作行为等价。
- 不得把人工补丁自动升级为全局规则。
- 源/目标 revision 不得漂移。
- 认证失败不得生成“迁移成功”表述。

## 依赖技能

- `elmos-project-intelligence-graph`
- `elmos-impact-analysis`
- `elmos-incremental-analysis-cache`

## 预期交付物

- `conversion-mapping.json`
- `modernization-report.md`
- `migration-presentation.pptx`

## 完成定义

- [ ] 源目标主要 symbol 映射可导航。
- [ ] 转换前后图表与文档一致。
- [ ] 失败定位能跳到规则、代码和测试。
- [ ] 中断恢复不丢中间状态。
- [ ] E1-E5 认证状态由证据驱动。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
