---
name: source-map-and-trivia-registry
description: Register exact source ranges and mappings among native nodes, PSP symbols/types/references/calls, tokens, and comments. Use whenever traceability, diagnostics, patching, or formatting preservation depends on source evidence.
---

# Source Map and Trivia Registry

Read `../references/psp-v1.md` before acting.

Store half-open UTF-8 byte offsets, one-based lines, zero-based columns, file ID, native-node link, semantic entity links, and attached comment IDs. Preserve license headers, documentation, inline comments, formatter controls, type comments, directives, shebang/BOM/line-ending metadata, and unattached trivia. Prefer native trivia ownership, but retain ambiguous attachment rather than dropping content.

Validate range order, containment, file bounds, Unicode, CRLF/LF, and mapping referential integrity. Do not normalize whitespace or rewrite comments. Accept only when every mappable declaration and call has a source map, every comment remains queryable, and any mapping ambiguity is explicit.
