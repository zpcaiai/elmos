# UI 信息架构与关键交互

## 1. 主导航

```text
项目总览
代码阅读
功能地图
架构讲解
流程分析
数据分析
API 与事件
架构图表
架构文档
项目 PPT
项目报告
项目问答
变更影响
风险与技术债
安全
转换前后对比
任务中心
设置与治理
```

## 2. 全局顶部栏

- Project / System Workspace；
- Repository / Branch / Commit；
- 分析覆盖率与状态；
- 当前环境/运行证据窗口；
- 机器 ETA P50/P90；
- 搜索与问答；
- 分享/导出；
- 权限和数据分类。

## 3. 代码阅读器布局

```text
┌──────────────┬─────────────────────────────┬──────────────────┐
│ 文件/功能树   │ Monaco Code / Diff          │ 证据/讲解/调用链  │
│ 过滤/状态     │ Source / IR / Target        │ Claim/Trace/Test  │
└──────────────┴─────────────────────────────┴──────────────────┘
```

必须支持：

- 文件状态：未分析、已分析、低置信度、失败、人工修改、已认证；
- 深链 URL 固定 revision；
- 右键：定义、引用、调用、解释、影响、加入文档/图表；
- 代码和图表双向选中联动；
- 权限不足时不显示路径或摘要。

## 4. Architecture Explorer

- 左侧 View：Context、Container、Component、Module、Data、Deployment、Security；
- 中间可交互图；
- 右侧节点详情、证据、成员、规则、风险；
- Current/Target/Source/Target/Runtime 切换；
- 聚合、过滤、折叠、搜索、布局锁；
- 保存为 Diagram、文档章节或 PPT 页面。

## 5. Flow Explorer

- 入口选择；
- Happy/Error/Retry/Compensation；
- Business/Technical/Runtime；
- Timeline 或泳道；
- Step 详情显示代码、数据、状态、权限和 Trace；
- 未确认路径用虚线和置信度。

## 6. Artifact Editors

### Diagram

- 自动生成层；
- 人工 override 层；
- 布局锁/语义锁；
- 三方合并；
- 评论/审批；
- SVG/PNG/PDF/DSL 导出。

### Document

- 章节树；
- claim/evidence gutter；
- 自动/人工/锁定标记；
- 受影响章节预览；
- Markdown/DOCX/PDF/HTML；
- Git PR。

### Presentation

- Slide Navigator；
- 页面目的、主结论、证据、备注；
- 品牌模板；
- 可编辑图表；
- 锁定页和增量更新；
- PPTX/PDF。

## 7. 任务中心

显示：

- 阶段 DAG；
- 已完成单位/总单位；
- P50/P90 机器 ETA；
- Token、算力、存储和费用；
- 缓存命中；
- 暂停/恢复/取消/重试；
- 错误分类和修复建议；
- 检查点和输出；
- 人工审核工作量独立字段。

## 在线调试工作台

路由建议：`/projects/:projectId/revisions/:revisionId/debug/:sessionId`。

- 顶栏：revision、Runtime Profile、adapter、环境/安全模式、状态、TTL、控制按钮；
- 左栏：文件树、断点、Learning Mission；
- 中央：Monaco、执行行、Inline Values、代码/源映射；
- 右栏：线程、调用栈、Scopes、Variables、Watches、业务/架构上下文；
- 底栏：Console、Output、Timeline、Network、SQL、Cache、Messages、Files、Locks；
- Compare 模式：passing/failing 或 Source/Target 双时间线；
- 所有不支持/被策略禁止能力显式禁用并解释。
