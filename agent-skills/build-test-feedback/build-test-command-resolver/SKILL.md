---
name: build-test-command-resolver
description: "Resolve pinned wrapper-based restore, build, analysis, discovery, and test commands for a Batch 8 matrix. Use when converting target build metadata into sandbox command records."
---
# Build Test Command Resolver
Read `../references/batch-8-repair-loop.md`. Prefer project wrappers and locked dependency modes. Bind the executable, arguments, working directory, environment names, timeout, expected reports and tool version to each phase.

Use only tools declared by the target profile; do not enable every available Python analyzer or Node script. Separate test discovery from execution and incremental commands from the final full command. Do not change filters, warnings or analyzer settings to hide a failure. Return blocked when the command or report contract is ambiguous.
