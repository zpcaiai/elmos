# Elmos Auto Skill Router v1.0.0

This package makes Antigravity projects behave as if skills are automatically selected for each task without forcing every SKILL.md into every context window.

It installs:

- `.agents/skills/elmos-auto-skill-router/` — routing skill and helper scripts.
- an idempotent auto-routing block in `.agents/AGENTS.md` — persistent project rules.
- `.elmos/skill-router.json` — machine-readable routing configuration.
- `.agents/skills-index.json` — generated index of project/global skills.

## Recommended behavior

Antigravity keeps all installed skills discoverable and loads materially relevant skills on demand. This package adds project-level rules that make the agent proactively compose multiple relevant skills and treat security/trust skills as mandatory when applicable.

## Install into a project

```bash
unzip elmos-auto-skill-router-v1.0.0.zip
cd elmos-auto-skill-router
./install.sh /path/to/project
```

Then verify:

```bash
/path/to/project/.agents/skills/elmos-auto-skill-router/scripts/check_install.sh /path/to/project
```

Refresh the skill index:

```bash
python3 /path/to/project/.agents/skills/elmos-auto-skill-router/scripts/refresh_skill_index.py --root /path/to/project
```

Preview routing for a task:

```bash
python3 /path/to/project/.agents/skills/elmos-auto-skill-router/scripts/route_skills.py \
  --root /path/to/project \
  --task "continue the Spring modernization certification work"
```

Continue with Antigravity CLI:

```bash
/path/to/project/.agents/skills/elmos-auto-skill-router/scripts/continue-with-skills.sh \
  /path/to/project --run
```

Without `--run`, the script only prints the generated prompt.

## Global skills

The indexer also scans common Antigravity global skill roots when present:

- `~/.gemini/config/skills/`
- `~/.gemini/antigravity-cli/skills/`
- `~/.agents/skills/`

Project skills still take precedence when names collide.

## Important

This package does **not** claim to force Antigravity to inject every skill body into every prompt. That would defeat progressive disclosure and cause context pollution. It implements an always-on router that discovers all skills and instructs the agent to load all materially relevant ones automatically.
