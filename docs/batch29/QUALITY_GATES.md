# Batch 29 Route Quality Gates

## Gate R29-A — Manifest and ownership

- route manifest validates
- directed source and target differ
- exact compiler/runtime versions are recorded
- route owner and review date exist
- support matrix exists

## Gate R29-B — Engine contracts

- source adapter emits valid PSP
- PSP/UIR references and source locations are valid
- output is deterministic for identical inputs
- target emitter consumes versioned contracts
- no direct control-plane database coupling

## Gate R29-C — Semantic safety

- critical semantic capabilities have executable evidence
- unsupported semantics are explicit
- unknown types are not collapsed to permissive catch-all types
- no silent semantic drops
- compatibility runtime remains inside budget

## Gate R29-D — Real target execution

- real target compiler/runtime invoked
- representative vertical slice builds
- required tests run
- generated public symbols have source trace
- test-integrity violations are zero

## Gate R29-E — Independent evidence

- holdout corpus is physically separate
- holdout cases were not used to author rules
- at least one representative or real repository case exists
- critical behavior regressions are zero
- unknown critical differences are zero

## Gate R29-F — Security, maintenance, and economics

- added dependencies have license/security evidence
- runtime components have owners and version policy
- cost per verified workload is visible
- expected manual effort is visible
- route has a support/maintenance owner

## Certification outcomes

- `certified`: all required gates pass for declared scope
- `limited`: safe, useful subset with explicit conditions
- `experimental`: evidence is promising but not sufficient for customer commitments
- `blocked`: a critical safety or correctness requirement fails
