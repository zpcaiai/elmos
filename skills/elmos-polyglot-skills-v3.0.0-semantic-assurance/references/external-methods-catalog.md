# External Methods Catalog (design references only)

Pinned tool/version selection belongs in each runtime adapter; do not vendor third-party code from this document without license review.

| Method | Reference | ELMOS adoption |
|---|---|---|
| Verified semantic preservation | https://compcert.org/ | semantic preservation theorem shape; verified-lowering option for supported C subsets |
| LLVM translation validation | https://github.com/AliveToolkit/alive2 | refinement checking and counterexample-based translation validation for suitable LLVM-level fragments |
| Executable formal semantics | https://kframework.org/ | executable semantics / rewrite-rule modeling for difficult language subsets and semantic reference oracles |
| Lossless/incremental parsing | https://tree-sitter.github.io/tree-sitter/ | CST fallback, error-tolerant parsing, grammar-based corpus generation; cross-check with native frontends |
| Polyglot language implementation | https://www.graalvm.org/ | language interoperability concepts and TCK-style cross-language tooling where applicable |
| Defined-behavior C generation | https://github.com/csmith-project/csmith | random C programs intended for differential compiler testing |
| Defined-behavior C/C++ generation | https://github.com/intel/yarpgen | optimization-stressing generated programs without UB by design |
| Rust UB interpretation | https://github.com/rust-lang/miri | unsafe Rust and memory-model/runtime invariant checks |
| Native sanitizers | https://clang.llvm.org/docs/AddressSanitizer.html and https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html | memory/UB detection in native runtime labs |
| Data-race sanitizer | https://clang.llvm.org/docs/ThreadSanitizer.html | concurrency evidence for applicable native routes |
| Symbolic execution | https://klee.llvm.org/ | bounded symbolic exploration for LLVM-based fragments |
| Property-based testing | https://hypothesis.readthedocs.io/ | generated inputs, stateful properties and shrinking patterns |
| Syntax-aware reducer | https://github.com/uw-pluverse/perses | minimize compiler/converter failures while retaining syntactic validity |
| ECMAScript conformance | https://github.com/tc39/test262 | normative clause-to-executable conformance-corpus pattern |
| WebAssembly semantics/tests | https://webassembly.org/specs/ | portable specified low-level execution/validation oracle and official spec tests |
| Verification-aware language | https://dafny.org/ | pre/post/invariant/proof-obligation patterns and specification-driven verification |

These references motivate implementation patterns; no external tool's presence automatically certifies an ELMOS route.
