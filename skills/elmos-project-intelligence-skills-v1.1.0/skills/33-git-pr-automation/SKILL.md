---
name: elmos-git-pr-automation
description: 把生成的文档、图表源、规则、修复或转换结果以安全、可审阅的 Git 分支和 Pull Request 交付。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: platform
  title_zh: Git、文档 PR 与变更交付自动化
  batch: BATCH-08-cache-versioning-git
  owner: elmos-project-intelligence
---

# Git、文档 PR 与变更交付自动化

## 目标

用最小权限和幂等工作流将 Elmos 输出纳入正常代码审查。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- repository/revision
- selected artifact or patch
- branch policy
- reviewers

## 必须输出

- branch/commit
- PR
- checks
- rollback/audit record

## 执行流程

1. 确认目标仓库、base revision、写权限和分支策略。
2. 创建唯一工作树/分支并应用最小变更。
3. 运行格式、链接、Schema、测试和敏感信息检查。
4. 生成结构化 commit 与 PR 描述，附影响和证据。
5. 设置 reviewer、labels 和 required checks。
6. 处理重复调用、base 更新、冲突和关闭回滚。

## 实施要求

- 默认创建草稿 PR，不直接合并。
- 外部副作用使用 idempotency key。
- 支持 GitHub、GitLab、Gitee 与通用 Git fallback。
- 文档 artifact 源文件与渲染输出策略可配置。
- PR 绑定 analysis run 和 artifact versions。

## 安全与可信度约束

- 不得 force push 用户分支。
- 不得提交密钥、临时缓存或未授权源代码副本。
- 不得绕过分支保护。

## 依赖技能

- `elmos-artifact-versioning-human-lock`
- `elmos-impact-analysis`

## 预期交付物

- `git-delivery-policy.md`
- `pr-template.md`
- `git-integration-tests.md`

## 完成定义

- [ ] 重复请求只产生一个有效 PR。
- [ ] base 变化能重新基线或明确冲突。
- [ ] PR 检查失败会阻止完成状态。
- [ ] 审计可追踪到发起用户和生成版本。
- [ ] 关闭/取消后资源被正确清理。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
