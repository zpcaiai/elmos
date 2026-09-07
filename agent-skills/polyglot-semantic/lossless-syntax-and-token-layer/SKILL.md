---
name: lossless-syntax-and-token-layer
description: Build the lossless native CST, token, comment, directive, trivia, and source-position layer for Batch 2. Use for parser recovery, patch traceability, Unicode/CRLF positioning, or any semantic analysis that needs exact source evidence.
---

# Lossless Syntax and Token Layer

Read `../references/psp-v1.md` before acting.

Prefer native lossless trees, then native AST, then Tree-sitter/ELMOS fallback. Detect UTF-8 BOM and line endings; retain tokens, whitespace/trivia, comments, documentation, directives, missing tokens, recovery nodes, and native kinds. Generate node IDs from snapshot/path/parser/kind/UTF-8 byte range and map fallback nodes to native nodes when both exist.

Do not format source, discard comments, or treat recovery nodes as complete semantics. Token/comment contents belong in content hashes, not logs. Emit file, token, comment, syntax-node, source-map, parser diagnostics, fallback status, and completeness metrics. Accept only when declarations and comments are locatable, Unicode and CRLF ranges are correct, ranges are within the file, and malformed files still produce explicit partial evidence.
