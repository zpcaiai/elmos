# Uninstall

Remove the installed skill directory:

```bash
rm -rf .agents/skills/elmos-auto-skill-router
```

Remove `.elmos/skill-router.json` and `.agents/skills-index.json` if no other tooling uses them.

In `.agents/AGENTS.md`, remove the block between:

```text
<!-- ELMOS_AUTO_SKILL_ROUTER_BEGIN -->
<!-- ELMOS_AUTO_SKILL_ROUTER_END -->
```
