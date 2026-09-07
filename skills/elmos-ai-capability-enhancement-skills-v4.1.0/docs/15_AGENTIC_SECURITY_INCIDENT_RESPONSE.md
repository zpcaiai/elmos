# Agentic Security and Incident Response

## Dedicated threat surfaces

- Skill/Plugin/MCP supply chain;
- RAG and long-term memory poisoning;
- prompt/tool injection and confused deputy;
- recursive delegation, loops and economic denial of service;
- multi-tenant data and identity crossing;
- managed-platform permission and region drift.

## Containment

Kill switches exist at run, agent, tool, tenant, provider and global scopes. Containment is durable and monotonic. Evidence is frozen before cleanup, credentials are rotated, active runs are fenced and cancelled, external side effects are reconciled, and safe restart requires independent approval.
