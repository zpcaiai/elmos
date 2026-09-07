---
name: polyglot-build-matrix-planner
description: "Plan a minimum sufficient Java, Python, C#, JavaScript, or TypeScript build and test matrix. Use when translating Batch 8 target modules into reproducible execution units."
---
# Polyglot Build Matrix Planner
Read `../references/batch-8-repair-loop.md`. Cover every target module and declared deployment platform, runtime, target framework and actual module mode. Include restore, build-model, compile, static analysis, discovery, layered tests and full regression.

Reduce the matrix from deployment targets, affected modules, high-risk concerns and conditional dependencies; do not run an unexplained Cartesian product. Never omit a security-critical module to save time. Record every reduction reason and a deterministic matrix ID.
