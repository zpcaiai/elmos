---
name: javascript-typescript-semantic-adapter
description: Extract JavaScript and TypeScript syntax and semantics with the TypeScript Compiler API plus Babel for PSP v1. Use for tsconfig/package projects, ESM/CommonJS, JSX/TSX, declaration files, structural types, async code, and dynamic module risk.
---

# JavaScript/TypeScript Semantic Adapter

Read `../references/psp-v1.md` before acting.

Use the pinned TypeScript Program/TypeChecker for binding and types, and Babel only for syntax extensions the configured compiler cannot parse. Honor tsconfig project references, module resolution, path aliases, package exports, declaration files, JSX/TSX, strictness, and JS check modes without running modules or lifecycle scripts. Preserve structural types, unions/intersections, conditional/mapped/template literal types, overloads, narrowing, classes/interfaces, prototypes, closures, async/promises, and import/export relations.

Do not merge ESM and CommonJS semantics. Record `any`, `unknown`, dynamic properties, prototype mutation, `eval`, `Function`, Proxy, computed imports, and unresolved packages explicitly. Babel syntax never substitutes for TypeChecker authority. Emit PSP core plus JS/TS extensions; accept only with traceable project configuration and honest dynamic/candidate resolution.
