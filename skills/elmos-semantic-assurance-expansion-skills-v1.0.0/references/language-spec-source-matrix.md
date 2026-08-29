# Language / Runtime Specification & Conformance Source Matrix

This registry tells implementation agents to prefer normative specifications and official/native conformance assets when building corpus mappings. Pin exact edition/version in executable evidence.

| Family | Preferred sources | ELMOS use |
|---|---|---|
| C/C++ native | ISO/vendor specs, compiler AST, sanitizers, LLVM IR tools | syntax/type/UB/ABI/translation validation |
| Rust | Rust reference/compiler/Miri | ownership, unsafe UB, layout/runtime checks |
| Java/Kotlin | language/JVM specs, JDT/K2/FIR, JVM tools | typing, generics, memory model, bytecode/API |
| C#/.NET | language/runtime specs, Roslyn | overload/type/reflection/async/runtime |
| JavaScript/TypeScript | ECMA-262 + Test262, TypeScript compiler | observable language behavior and type layer |
| WebAssembly | official spec/reference interpreter/test suite | portable low-level semantics oracle |
| Swift/Objective-C | compiler/runtime/ABI docs | ARC, ABI, dispatch, interop |
| COBOL/RPG/PL-I | vendor compiler/runtime manuals and owned native labs | decimal, records, batch/transaction semantics |
| Fortran | language/compiler + numeric libraries | array/numeric/HPC semantics |
| Ada/SPARK | language reference + proof toolchain | contracts, ranges, safety proof obligations |
| ABAP/Natural/ABL/PowerBuilder/VB6/xBase | vendor/runtime documentation + authorized native labs | 4GL/data/UI/transaction behavior |
