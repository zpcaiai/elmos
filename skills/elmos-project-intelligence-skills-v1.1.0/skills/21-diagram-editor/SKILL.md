---
name: elmos-diagram-editor
description: 实现基于 Diagram Spec 的在线图表画布、节点编辑、布局调整、评论、版本比较和人工锁定。用于自动生成后的审阅与维护。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: artifacts
  title_zh: 在线图表编辑与人工锁定
  batch: BATCH-05-diagram-platform
  owner: elmos-project-intelligence
---

# 在线图表编辑与人工锁定

## 目标

让用户编辑语义而非破坏性修改图片，并在重新生成时安全合并自动变化。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Diagram Spec/version
- 用户权限
- 自动新版本
- 主题/布局

## 必须输出

- edited spec
- manual overrides
- merge result
- review history

## 执行流程

1. 实现缩放、平移、搜索、折叠、下钻和 mini-map。
2. 支持节点重命名、说明、分组、移动、隐藏和手工连线。
3. 区分事实字段、展示字段和建议字段的编辑权限。
4. 保存人工 override 和锁定范围。
5. 对新自动 Spec 进行三方合并并显示冲突。
6. 支持评论、审批、撤销/重做和版本回退。

## 实施要求

- 人工编辑以 patch/override 存储，不修改原分析事实。
- 布局锁和语义锁分离。
- 节点删除需区分从视图隐藏与声明不存在。
- 多人编辑至少支持乐观锁和冲突提示。
- 导入导出保留 stable IDs。

## 安全与可信度约束

- 不得静默覆盖人工锁定。
- 低权限用户不能改变 Confirmed 事实。
- 恶意 SVG/文本必须消毒。

## 依赖技能

- `elmos-diagram-rendering`
- `elmos-artifact-versioning-human-lock`

## 预期交付物

- `apps/insight-web/src/modules/diagram-editor`
- `diagram-merge-tests.md`

## 完成定义

- [ ] 自动再生成后布局和锁定内容正确保留。
- [ ] 冲突可逐项解决并审计。
- [ ] 撤销/重做覆盖核心操作。
- [ ] 图节点点击可回代码和证据。
- [ ] 导出再导入不丢人工 override。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
