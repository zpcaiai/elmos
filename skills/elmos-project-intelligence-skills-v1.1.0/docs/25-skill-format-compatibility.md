# Agent Skills 兼容说明

本包使用跨宿主最小前置字段：

```yaml
---
name: elmos-example
description: 说明该技能做什么、何时使用。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex and Claude Code.
metadata:
  version: 1.0.0
---
```

每个 Skill 目录结构：

```text
skill-name/
├── SKILL.md
├── references/
│   ├── module-spec.md
│   └── usage.md
└── agents/
    └── openai.yaml
```

## Codex

仓库级安装目标：`.agents/skills/`。  
技能名可在 Codex 中使用 `$elmos-...` 显式调用。

## Claude Code

仓库级安装目标：`.claude/skills/`。  
目录名成为 `/skill-name` 命令；本包安装时保留目录名和 `name`。

## 设计原则

- `description` 前置主要触发条件；
- 每个 Skill 聚焦一个任务域；
- 详细需求放在 `references/module-spec.md`，控制 SKILL.md 上下文成本；
- 确定性校验使用 `scripts/`；
- 安装器可按 profile 选择子集，避免一次加载过多技能描述；
- 不使用仅某一宿主支持的动态 shell/frontmatter 作为核心依赖。

## 官方依据（访问日期：2026-08-19）

- OpenAI Codex “Build skills”：Skill 为包含 `SKILL.md`、可选 scripts/references/assets 的目录；仓库路径为 `.agents/skills`。
- Anthropic Claude Code “Extend Claude with skills”：Skill 以 `SKILL.md` 为入口，项目路径为 `.claude/skills`，可带 templates/examples/scripts/references。
