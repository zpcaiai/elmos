---
name: target-language-body-emitters
description: Implement or invoke target AST/LST/CST emitters for Java, Python, C#, TypeScript, and JavaScript method bodies. Use after a complete lowering plan exists and whenever generated code must parse deterministically.
---
# Target Language Body Emitters
Read `../references/lowering-v1.md`. Implement the common type/statement/expression/body/import/comment/source-map/parse/format interface with OpenRewrite or JavaParser, Roslyn, LibCST plus Python AST validation, and TypeScript Factory/Printer/Program. Give JavaScript an explicit ESM/CommonJS/JSDoc/runtime-guard policy.

The emitter executes plans; it never invents business semantics or dependencies. Avoid large raw string templates as the primary mechanism. Enforce target versions, reparse after formatting, update source maps and make output deterministic. Missing native backend blocks the callable.
