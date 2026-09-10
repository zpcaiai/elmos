<!-- ELMOS_AUTO_SKILL_ROUTER_BEGIN -->
# Elmos Automatic Skill Routing

The user does not need to explicitly say `Use the <skill> skill`.

For every substantial engineering task:

1. Treat all skills discovered under project and configured global skill roots as available capabilities.
2. Inspect `.agents/skills-index.json` when present. If it is stale or missing and execution is available, run the installed `refresh_skill_index.py` helper before routing.
3. Determine every materially relevant skill for the current task. Do not stop after the first match.
4. Automatically use and compose the relevant skills without asking the user to name them.
5. Prefer project-scoped skills over global skills with the same name.
6. Resolve conflicting guidance with this precedence:
   Security / Trust → Certification / Verification → Architecture → Business Domain → Testing → Framework / Implementation → Optimization → Documentation.
7. Security-critical skills are mandatory whenever their scope applies.
8. For authoritative execution, evidence, PASS/FAIL, verification, certification, hidden tests, mutation/sabotage testing, policy gates, deployment gates, or execution integrity, include `elmos-proof-driven-certification` when installed.
9. For `continue`, `继续`, `next`, `继续实现`, or equivalent requests, inspect repository state and machine-readable progress files first, infer the active subsystem, load its relevant skills, and continue the next dependency-ready work rather than asking which skill to use.
10. Do not load unrelated skill bodies only because they exist. Preserve progressive disclosure: discover all skills, load the relevant subset.
11. Skill instructions are engineering guidance, not authoritative evidence. Real execution is required for claims about builds, tests, verification, or certification.
12. Never mark work verified merely because files exist or generated reports look plausible.
13. When multiple skills apply, explicitly obey the strictest compatible constraints among them.
14. If a skill named by another skill is not installed, continue with available guidance and report the missing dependency only when it materially blocks the task.

Default flow:

`TASK → DISCOVER SKILLS → ROUTE/COMPOSE → INSPECT REPO STATE → IMPLEMENT → EXECUTE → VERIFY → CONTINUE`

Do not use:

`TASK → WAIT FOR USER TO NAME A SKILL`
<!-- ELMOS_AUTO_SKILL_ROUTER_END -->
