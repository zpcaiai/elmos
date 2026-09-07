---
name: api-semantic-profile-builder
description: Convert observed dependency API use into semantic requirements and a stable fingerprint. Use to compare cross-ecosystem candidates.
---
# API Semantic Profile Builder
Read `../references/dependency-migration-v1.md`. Build requirements for signatures, data/null/numeric/time/path/regex semantics, error channels, ordering, determinism, state, thread safety, async/cancellation/backpressure, lifecycle, resources, serialization, transactions, security and performance-sensitive behavior. Bind every requirement to used APIs and evidence. Emit a deterministic fingerprint, confidence, criticality and unresolved dimensions. Do not assume same-named operations or serializable types behave alike; unknown high-impact semantics block automatic mapping.
