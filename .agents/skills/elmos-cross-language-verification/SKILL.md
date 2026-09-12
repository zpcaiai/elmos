---
name: "elmos-cross-language-verification"
description: "Verify behavioral equivalence between source and target code in different languages through automated test generation, multi-language execution, and output comparison."
---

# ELMOS Cross-Language Verification

This skill is designed to systematically verify that code migrated or translated from one language to another maintains strict behavioral equivalence. It automates the generation of test vectors, runs them against both the original and translated implementations, and compares the outputs to ensure fidelity.

## When to Use
- Validating an automated migration of a component from Python to Go, or Java to C#.
- Ensuring algorithmic implementations across multiple language runtimes produce identical results.
- Detecting subtle precision, encoding, or floating-point discrepancies between language ecosystems.

## Capabilities
- **Verification Workflow:** Orchestrates the build, run, and comparison phases across language boundaries.
- **Supported Language Pairs:** Java <-> C#, Python <-> Go, TypeScript <-> Python, and other combinations supported by the engine.
- **Test Generation:** 
  - Boundary value analysis
  - Property-based testing
  - Roundtrip serialization/deserialization testing
- **Output Comparison:** Structural and semantic comparison of STDOUT, STDERR, exit codes, and returned data structures, with configurable tolerance for floating-point values.
- **Report Generation:** Produces detailed variance reports pinpointing the exact input vectors that caused behavioral divergence.

## Usage
Use the `elmos-cross-verify` CLI to run the verification process.

```bash
elmos-cross-verify run --source src/python/alg.py --target src/go/alg.go --suite tests.json
elmos-cross-verify generate-tests --source src/python/alg.py --output tests.json
elmos-cross-verify report --run-id 12345
```

## Engine Location
`engines/cross-language-verification-engine/`

## Integration
Acts as the validation and quality assurance layer for `elmos-multilang-project-generation` and legacy modernization skills.
