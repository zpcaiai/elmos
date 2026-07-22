---
name: control-flow-summary-extractor
description: Extract language-neutral control-flow summaries for every callable while retaining native CFG references. Use for Batch 3 preparation, effect/risk analysis, exception paths, loops, pattern branches, async, and generators.
---

# Control Flow Summary Extractor

Read `../references/psp-v1.md` before acting.

Use native compiler/semantic control-flow APIs when available and syntax-backed conservative summaries otherwise. Emit entry, blocks, edges, exits, and structures for sequence, branch, switch/match, loops, break/continue, return, throw, try/catch/finally, resource scopes, short-circuiting, pattern guards, yield, await, and unreachable/recovery regions. Record effects such as mutation, I/O indication, exception, suspension, and allocation only when evidenced.

Do not turn a summary into a claim of behavioral equivalence or invent executable expressions. Keep native CFG references and list unsupported constructs. Every block/range must lie in its callable/file, edges must reference existing blocks, and exit/exception/async semantics must remain explicit.
