# 00 — Package Scope and Boundaries

## Product objective

Elmos should cover the recurring operating loop of a strong Forward Deployed Engineer and repository transformation team:

```text
qualify → discover → scope → access → reproduce → understand → assess → prioritize
→ design → implement → verify → prepare rollout → support → adopt → hand off → learn
```

The package converts that loop into typed, durable and auditable product capabilities. It does not replace business, legal, security, production or domain accountability.

## Honest promise

“Any source code, all problems” is replaced by a measurable contract:

- inventory every accessible artifact;
- declare S0–S5 support depth per component;
- declare E0–E3 evidence per claim in this package;
- report detected issues and evidence;
- report classes tested and verified absent;
- report unknown and unsupported coverage explicitly;
- prevent unqualified completeness and production claims.

## Product modes

1. **Discover** — customer workflow, outcome, data and scope.
2. **Assess** — read-only repository/runtime analysis.
3. **Plan** — target architecture and Transformation DAG without edits.
4. **Supervised transform** — workspace-only atomic ChangeSets.
5. **Verify** — independent E0–E3 evidence production.
6. **Release preparation** — shadow/canary/rollback rehearsal, no production cutover authority.
7. **Continuous governance** — portfolio health, drift, incidents, adoption and reusable learning.

## Fixed boundaries

- 0 new routable entry points.
- 0 duplicate canonical authorities.
- E3 standalone maximum.
- Production writes prohibited.
- Adapters are replaceable and cannot self-certify.
- Package validation is not target implementation validation.
