---
name: public-api-inventory
description: Inventory public HTTP and Java contracts before modernization. Use for controller routes, exported Java types, serialization surfaces, OpenAPI baselines, or API compatibility gates.
---
# Public API Inventory

## Workflow
1. Inventory controller mapping annotations and public types in API packages.
2. Normalize signatures without executing application code.
3. Attach OpenAPI or binary API artifacts when available.
4. Preserve source location, owner, kind and evidence digest.

## Acceptance
- Dynamic routing remains `INCONCLUSIVE` until runtime evidence exists.
- Inventory changes require API review before plan completion.
- No compatibility claim is made from presence-only scanning.

