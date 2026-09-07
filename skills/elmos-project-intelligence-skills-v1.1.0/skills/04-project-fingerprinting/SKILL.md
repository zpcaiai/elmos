---
name: elmos-project-fingerprinting
description: 识别项目语言、框架、构建系统、入口、数据库、消息、部署和生成代码。用于分析规划、解析器选择和机器 ETA 估算。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: ingestion
  title_zh: 项目指纹与技术栈识别
  batch: BATCH-01-ingestion-and-parsing
  owner: elmos-project-intelligence
---

# 项目指纹与技术栈识别

## 目标

生成可靠的技术栈与项目复杂度指纹，为后续分析选择正确工具链。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Project Revision manifest
- 文件样本
- 构建/锁文件
- 配置与容器文件

## 必须输出

- technology-fingerprint.json
- 语言/框架置信度
- 分析计划候选
- 复杂度特征

## 执行流程

1. 统计语言、文件、LOC、生成代码和测试占比。
2. 识别构建系统、包管理器、框架和版本。
3. 识别服务入口、UI 入口、CLI、Cron、Consumer 和 Webhook。
4. 识别数据库、缓存、消息、云资源和部署描述。
5. 识别反射、动态加载、宏、代码生成和 FFI 风险。
6. 输出解析器与运行时证据采集建议。

## 实施要求

- 支持 Java、Kotlin、Python、C#、Go、Rust、C++、PHP、JavaScript、TypeScript、React、Vue、Objective-C、Swift、Flutter/Dart。
- 每项识别附来源文件与置信度。
- 区分声明依赖与实际引用依赖。
- 识别 Monorepo workspace 边界。
- 输出初始分析机器 wall-clock P50/P90 的特征，不直接虚构耗时。

## 安全与可信度约束

- 文件扩展名不能作为唯一框架证据。
- 锁文件和 manifest 冲突时必须报告。
- 动态行为无法静态确认时标记风险。

## 依赖技能

- `elmos-repository-ingestion`

## 预期交付物

- `technology-fingerprint.json`
- `analysis-plan.json`

## 完成定义

- [ ] 主语言与构建系统在基准仓库识别准确率达到目标阈值。
- [ ] 所有技术栈结论可跳转到证据文件。
- [ ] 错误识别可人工覆盖且被版本化。
- [ ] 分析计划明确列出不支持或低置信度区域。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
