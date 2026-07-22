---
name: expression-lowering-and-emission-planner
description: Plan UIR expressions as target AST expressions or ordered statement preludes plus a result. Use for invocations, member/index access, conversions, await/yield, queries, dynamic expressions, or complex effectful expressions.
---
# Expression Lowering and Emission Planner
Read `../references/lowering-v1.md`. For each non-opaque expression, produce prelude statements, one result expression, cleanup, generated node IDs and source maps. Respect parentheses/precedence and split expressions when effects, null propagation, awaits, conversions, exception wrapping or resource management exceed the target expression budget.

Never duplicate effectful access or optimize for a single line. Treat properties and indexers as potentially effectful. Promote unsafe expressions to explicit statements. Pass structured nodes to the target emitter and reparse its output.
