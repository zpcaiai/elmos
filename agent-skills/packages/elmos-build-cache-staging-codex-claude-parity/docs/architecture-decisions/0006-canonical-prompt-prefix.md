# ADR-0006: Compile prompts into canonical stable and volatile segments

Status: accepted

## Decision

ELMOS will represent prompts as versioned typed segments. Stable system, policy, tool, output-schema, Skill, and repository-architecture segments precede a deliberate cache boundary; task, diff, retrieved file, and tool-result content follows it. Canonical serialization and a manifest make prefix changes explainable.

## Consequences

- Exact provider-prefix reuse can be measured and optimized.
- Any tool/policy/schema change deliberately creates a new compatibility group.
- Volatile run IDs, times, paths, and environment data cannot silently poison the prefix.
- Prompt construction becomes tested code rather than ad-hoc string concatenation.
