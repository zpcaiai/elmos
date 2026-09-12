# Installation Notes

Project installation is the default because the router modifies project `.agents/AGENTS.md`.

Installed files:

```text
<project>/.agents/AGENTS.md
<project>/.agents/skills/elmos-auto-skill-router/
<project>/.agents/skills-index.json
<project>/.elmos/skill-router.json
```

The installer replaces only the block between:

```text
<!-- ELMOS_AUTO_SKILL_ROUTER_BEGIN -->
<!-- ELMOS_AUTO_SKILL_ROUTER_END -->
```

Existing AGENTS.md content outside that block is preserved.

Run the installer again to upgrade idempotently.
