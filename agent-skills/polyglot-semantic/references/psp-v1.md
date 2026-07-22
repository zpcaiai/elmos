# PSP v1 operating contract

Batch 2 understands the immutable Batch 1 snapshot. It does not choose a target, generate target-language code, repair builds, or claim behavioral equivalence.

## Three layers

1. Preserve tokens, comments, directives, trivia, native node kinds, UTF-8 byte ranges, and line/column ranges.
2. Obtain symbols, types, scopes, overloads, calls, inheritance, and control-flow facts from a language authority.
3. Wrap common facts in PSP v1 while retaining language-native facts under `languageExtensions`.

Use Eclipse JDT/Javac/JavaParser/OpenRewrite for Java, LibCST plus Pyright for Python, Roslyn for C#, and the TypeScript Compiler API plus Babel for JavaScript/TypeScript. Tree-sitter or the ELMOS lossless tokenizer is syntax-only fallback evidence. It is never authoritative binding evidence.

## Trust and execution boundary

- Bind every run to one passed Batch 1 snapshot and verify current file hashes.
- Do not execute repository code, lifecycle scripts, imports, annotation processors, source generators, unknown analyzers, or JavaScript modules.
- Run native analyzers only through the isolated workspace/engine port with pinned provider version, resource budget, and no ambient credentials.
- Record provider, provider version, method, resolution level, confidence, input hashes, and analysis profile.
- Represent ambiguity as candidate sets, dynamic, unresolved, or diagnostics. Never fabricate exactness.

## Identity and positions

Derive IDs from canonical, versioned inputs. File IDs bind snapshot and normalized path. Node IDs bind snapshot, path, parser family, native kind, and UTF-8 byte range. Declaration symbols bind language, project, and authoritative symbol key. Local symbols also bind enclosing callable and declaration range. Cache keys bind snapshot/file hash, analyzer/config versions, and dependency environment.

Ranges use half-open UTF-8 byte offsets plus one-based lines and zero-based columns. Hash token/comment text rather than placing source contents in manifests or logs.

## PSP v1 artifacts

Write `semantic/semantic-run-manifest.json`, `protocol-version.json`, Zstandard JSONL entity streams, per-language extension streams, `metrics.json`, and `indexes/semantic-index.sqlite`. Write conformance, unresolved-symbol, dynamic-feature, coverage, and call-graph reports under `reports/`. JSON Schema is the auditable source of truth; JSONL order carries no meaning.

## Gates

- Gate A: syntax parse rate >= 0.98, source-map coverage >= 0.99, symbol resolution >= 0.90 (language-adjustable for dynamic projects).
- Gate B: Gate A, type resolution >= 0.85, unresolved calls <= 0.10, and zero blocking diagnostics.
- Gate C: Gate B, type resolution >= 0.95, symbol resolution >= 0.98, dynamic calls <= 0.05, and source maps >= 0.995.

Apply gates per module. A fallback-provider diagnostic is blocking even when its lossless syntax coverage is excellent. Only a conformant module may enter Batch 3; only Gate B permits automatic translation.
