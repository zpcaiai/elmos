---
name: elmos-online-code-reader
description: 实现以阅读和证据导航为核心的浏览器代码工作台。用于文件树、代码查看、Diff、书签、评论和跨视图联动；不等同于完整通用在线 IDE。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: experience
  title_zh: 在线代码阅读器
  batch: BATCH-03-code-reader-and-explanation
  owner: elmos-project-intelligence
---

# 在线代码阅读器

## 目标

提供快速、安全、可扩展的项目代码阅读入口，并与架构、流程、数据和转换结果双向联动。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Project Revision
- 文件内容 API
- Code Graph
- 用户权限与偏好

## 必须输出

- Vue/Monaco 阅读器
- 文件树与标签页
- Diff 视图
- 阅读状态与审计

## 执行流程

1. 建立项目/仓库/分支/Commit 选择器和虚拟化文件树。
2. 接入 Monaco，支持高亮、折叠、大纲、面包屑、多标签和分屏。
3. 实现原始/目标、Commit/Commit、自动/人工修改 Diff。
4. 实现深链：文件、行、Symbol、Claim、Diagram Node。
5. 加入书签、私人笔记、团队评论、最近阅读和收藏。
6. 接入权限、脱敏、审计和大文件降级。

## 实施要求

- 首屏不得等待整个项目分析完成。
- 文件内容分块/流式加载，支持大文件和二进制预览策略。
- URL 可复制并固定 revision，避免链接漂移。
- 源代码只读为默认；编辑能力单独授权。
- 图表节点、文档引用和问答答案能定位到精确行。

## 安全与可信度约束

- 禁止浏览器获得仓库主凭据。
- 未经权限不得显示文件路径、符号名或搜索片段。
- 代码渲染必须防 XSS 和恶意 Unicode 混淆。
- 不得用当前分支内容替换固定 revision 链接。

## 依赖技能

- `elmos-repository-ingestion`
- `elmos-symbol-code-graph`

## 预期交付物

- `apps/insight-web/src/modules/code-reader`
- `code-reader-e2e-report.md`

## 完成定义

- [ ] 100k 文件项目文件树可交互且不冻结。
- [ ] 代码打开、标签切换和定位达到体验 SLO。
- [ ] 复制的深链在同权限用户下可复现。
- [ ] Diff 能区分自动生成、人工编辑和转换来源。
- [ ] 权限撤销后缓存内容不可继续访问。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。

## 在线调试联动

本技能仍以只读阅读为默认。安装 `debug` Profile 后，可从文件、符号、测试、流程或失败证据创建 `elmos-online-debug-workbench` 会话；阅读器不得自行启动未授权进程或开放任意终端。
