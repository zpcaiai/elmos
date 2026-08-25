---
name: elmos-repository-ingestion
description: 实现 Git/ZIP/本地目录/多仓库项目的安全接入、修订冻结和内容清单。用于首次导入、同步、分支切换和 Elmos 临时项目接入。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: ingestion
  title_zh: 仓库接入与修订冻结
  batch: BATCH-01-ingestion-and-parsing
  owner: elmos-project-intelligence
---

# 仓库接入与修订冻结

## 目标

把任意受支持项目转换为不可歧义、可重放、可审计的 Project Revision。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Git URL 或上传文件
- 认证引用
- 分支/Tag/Commit
- 包含/排除规则

## 必须输出

- Repository 记录
- 冻结 revision
- 内容 manifest
- 导入审计与错误报告

## 执行流程

1. 校验来源、租户、权限和内容大小。
2. 解析 Git、子模块、LFS、Monorepo 和多仓库组合。
3. 冻结 commit SHA；上传包计算内容哈希。
4. 扫描文件类型、二进制、生成代码、Vendor 与敏感文件。
5. 写入对象存储并生成不可变 manifest。
6. 发布 project.revision.ingested 事件。

## 实施要求

- 支持 GitHub、GitLab、Gitee、Bitbucket 与通用 Git。
- 凭据只通过 Secret Broker 获取且不得落入日志。
- 支持 include/exclude glob、最大文件和仓库配额。
- 重复导入相同内容必须命中内容寻址存储。
- 导入失败必须提供可修复分类。

## 安全与可信度约束

- 禁止执行仓库代码。
- 默认忽略 .git、node_modules、target、build、vendor 二进制缓存。
- 检测到密钥只记录脱敏指纹，不回显内容。
- 不得自动切换到未请求分支。

## 依赖技能

- `elmos-reference-architecture`

## 预期交付物

- `project-manifest.json`
- `ingestion-report.json`

## 完成定义

- [ ] 相同 revision 重复导入得到相同 manifest hash。
- [ ] 断点续传不会产生重复对象。
- [ ] 子模块 revision 被明确记录。
- [ ] 私有凭据不出现在日志、事件或 artifact。
- [ ] 删除项目后按保留策略可验证清除。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
