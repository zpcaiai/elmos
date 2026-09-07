---
name: structured-control-flow-cfg-ssa-builder
description: Derive linked structured, CFG, and local-value SSA views. Use for flow analysis, narrowing, exception/finally, await/yield, or generation readiness.
---
# Structured Control Flow CFG SSA Builder
Read `../references/uir-v1.md`. Keep structured regions as generation truth and derive blocks, terminators, explicit normal/exception/finally/suspend/resume edges, block arguments/Phi, def-use, and flow facts. SSA local values only; model heap through effects. Preserve unreachable and language-special flow. Validate dominance, edge arguments/types, exits, finally coverage, and bidirectional structured/CFG links.
