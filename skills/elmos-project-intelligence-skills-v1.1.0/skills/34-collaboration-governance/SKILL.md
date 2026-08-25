---
name: elmos-collaboration-governance
description: 实现项目、仓库、文件、图表、文档、PPT、问答、导出和模型调用的协作与治理。用于企业团队、外部客户和审计人员。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: enterprise
  title_zh: 协作、RBAC、审批与审计
  batch: BATCH-09-collaboration-and-connectors
  owner: elmos-project-intelligence
---

# 协作、RBAC、审批与审计

## 目标

提供最小权限、可委派、可审计的多角色协作体验。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- tenant/org/project
- identity/role
- resource/action
- sharing/approval policy

## 必须输出

- RBAC/ABAC policies
- comments/reviews
- share links
- audit events

## 执行流程

1. 定义管理员、架构师、开发、测试、运维、安全、产品、访客、客户、审计等角色。
2. 细化 project/repo/revision/file/artifact/claim/export/model 权限。
3. 实现评论、@、任务、订阅、审批和通知。
4. 实现带有效期、水印、范围和撤销的分享。
5. 为读取、搜索、生成、导出、修改和认证记录审计。
6. 接入 SSO、SCIM、MFA 与组织策略。

## 实施要求

- 服务端每次查询执行授权，不能依赖前端隐藏。
- 图谱搜索需做 node/edge/evidence 级过滤。
- 权限变更应快速使缓存和链接失效。
- 外部访客默认无法查看原始代码。
- 审批职责支持分离。

## 安全与可信度约束

- 不得允许 Artifact 链接绕过源文件权限。
- 不得让同一主体在高风险流程中同时生成和认证。
- 审计日志不可由普通管理员修改。

## 依赖技能

- `elmos-reference-architecture`
- `elmos-security-threat-model`

## 预期交付物

- `rbac-matrix.csv`
- `audit-event-schema.json`
- `governance-tests.md`

## 完成定义

- [ ] 权限矩阵自动测试覆盖允许与拒绝。
- [ ] 撤销后分享和缓存访问失效。
- [ ] 跨租户查询红队无泄漏。
- [ ] 审批职责分离生效。
- [ ] 审计事件包含 who/what/when/where/result。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
