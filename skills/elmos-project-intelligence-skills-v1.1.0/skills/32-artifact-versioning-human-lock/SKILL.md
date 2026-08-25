---
name: elmos-artifact-versioning-human-lock
description: 管理图表、文档、PPT、报告和解释的版本、草稿、审批、人工 override、锁定和三方合并。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: platform
  title_zh: Artifact 版本与人工内容保护
  batch: BATCH-05-diagram-platform
  owner: elmos-project-intelligence
---

# Artifact 版本与人工内容保护

## 目标

确保自动更新不会破坏人工维护内容，同时保持与代码 revision 的一致性。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- generated artifact
- previous base
- human edits
- new generated version

## 必须输出

- artifact versions
- locks/overrides
- merge conflicts
- approval history

## 执行流程

1. 定义 Artifact、Block、Element、Version、Lock、Override 和 Review 模型。
2. 为段落、图节点、PPT 页面和表格分配稳定 ID。
3. 保存 base-generated、human-patch 和 next-generated 三方数据。
4. 执行语义合并并分类自动可合并/冲突/失效。
5. 支持 Draft、Reviewed、Approved、Certified 生命周期。
6. 提供回滚、比较、审计和保留策略。

## 实施要求

- 锁定支持内容、语义、布局和整页/整章范围。
- 人工 override 与自动事实分离。
- Artifact 必须绑定 project revision、analysis run、template/model/generator version。
- 可生成 stale reason 和 regen preview。
- 审批签名不可由生成 worker 伪造。

## 安全与可信度约束

- 不得自动解决影响事实正确性的冲突。
- 不得删除历史版本以制造一致性。
- 权限下降后不得保留可读快照链接。

## 依赖技能

- `elmos-evidence-provenance`

## 预期交付物

- `artifact-schema.json`
- `merge-policy.md`
- `artifact-lifecycle-tests.md`

## 完成定义

- [ ] 三方合并核心场景通过。
- [ ] 锁定内容跨再生成保持。
- [ ] 每个版本可完整重建或验证。
- [ ] 审批和状态转换权限正确。
- [ ] stale artifact 不可误标 Certified。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
