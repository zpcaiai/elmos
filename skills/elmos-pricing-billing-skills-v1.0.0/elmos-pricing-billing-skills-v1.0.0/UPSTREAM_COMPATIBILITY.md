# Upstream Compatibility

## Agent Skills format

The package follows the open Agent Skills structure: each skill is a directory with `SKILL.md`, YAML frontmatter containing `name` and `description`, plus optional `references/`, `assets/`, and scripts. Skill names match parent directories and stay within the lowercase/hyphen constraints.

Reference: https://agentskills.io/specification

## OpenAI Codex

- Project skills install to `.agents/skills/<skill>/SKILL.md`.
- The distributable Codex plugin uses `.codex-plugin/plugin.json` and root `skills/`.
- The full package installer can place skills into a target repository.

References:
- https://developers.openai.com/codex/build-skills
- https://developers.openai.com/plugins/build/plugins

## Claude Code

- Project skills install to `.claude/skills/<skill>/SKILL.md`.
- The distributable Claude Code plugin uses `.claude-plugin/plugin.json` and root `skills/`.
- It can be tested with Claude Code's plugin-directory workflow or installed as project skills.

References:
- https://code.claude.com/docs/en/skills
- https://code.claude.com/docs/en/plugins

## Target application stack

The skills are intentionally stack-adaptive. They require the coding agent to preserve the target repository's established language, framework, database, migration tool, tests and deployment practices unless an approved ADR states otherwise. The bundled PostgreSQL/OpenAPI/AsyncAPI files are reference contracts, not a forced rewrite.
