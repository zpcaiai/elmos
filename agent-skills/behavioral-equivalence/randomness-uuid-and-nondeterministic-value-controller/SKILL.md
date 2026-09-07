---
name: randomness-uuid-and-nondeterministic-value-controller
description: "Control random numbers, UUIDs, sequences, generated IDs, temporary names and iteration order during Batch 9. Use when nondeterministic values cause or could hide source-target differences."
---

# Randomness UUID and Nondeterministic Value Controller

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Inventory deterministic and security-sensitive value sources.
2. Choose fixed seed, injected stream, record/replay, referential mapping or property comparison per source.
3. Record value order, call count and cross-observation mapping.

## Hard rules

- Never introduce a fixed cryptographic seed into production behavior.
- Preserve UUID and generated-ID referential integrity.
- Treat changed random call count as a possible behavior difference.

## Output

Emit value-stream manifests, mappings and unresolved nondeterminism.

