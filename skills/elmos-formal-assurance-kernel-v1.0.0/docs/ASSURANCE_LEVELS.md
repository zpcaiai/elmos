# Assurance Levels and Proof Status Semantics

## Assurance levels

| Level | Meaning | Typical evidence | May satisfy P0? |
|---|---|---|---|
| `NONE` | no usable assurance | missing, unsupported, unknown | No |
| `A0_TESTED` | executable tests/runtime assertions | tests, monitoring | Only as compensating control |
| `A1_BOUNDED` | no counterexample inside an explicit finite bound | TLC/Alloy/Kani/VeriEQL bounded run | Only when policy explicitly requires A1 |
| `A2_SOLVER_PROVED` | supported formula discharged by a trusted solver | SMT/VC log with pinned TCB | Yes for eligible properties |
| `A3_CERTIFIED` | independently kernel-checked proof certificate | Lean or other small-kernel proof | Yes |
| `A4_COMPOSED` | verified component results composed across interfaces | assume–guarantee graph | Yes |
| `TRUSTED` | A4 plus E1–E5, P05, current evidence, operations and customer Golden Route | signed evidence bundle | Yes |

## Canonical statuses

`PROVED_CERTIFIED` and `PROVED_INDUCTIVE` are strongest when their certificates/models are independently checkable. `PROVED_SOLVER_TRUSTED` trusts the exact pinned solver and adapter. `PROVED_FOR_SUPPORTED_FRAGMENT` is valid only for the declared language/query fragment.

`BOUNDED_NO_COUNTEREXAMPLE` means exactly what it says: the search found no counterexample inside the recorded scope. It does not prove behavior outside that scope.

`REFUTED_WITH_COUNTEREXAMPLE` is a useful result and must preserve the minimized witness. `UNKNOWN_TIMEOUT` and `UNKNOWN_RESOURCE_LIMIT` are not failures of the property, but they are failures to establish it. `UNSUPPORTED` and `ASSUMPTION_REQUIRED` define proof boundaries. `RUNTIME_MONITORED` is an operational control, not a static proof. `WAIVED_BY_APPROVER` is governance, not technical evidence.

## Anti-inflation rules

1. A bounded run cannot emit a proved status.
2. Unknown/unsupported/refuted statuses cannot carry A2 or higher assurance.
3. A stale result retains historical truth but cannot pass a current release gate.
4. Aggregate assurance is the weakest required critical result, not an average.
5. Waivers never rewrite the underlying result.
6. Reports and UI must render canonical status text and bounds.
7. “100% verified” is prohibited unless the entrypoint inventory, proof coverage and dynamic boundaries support that claim.

## Marketing-safe wording

Use:

> Critical properties listed in the evidence report were proved for the declared semantic profiles and assumptions; bounded and runtime-monitored boundaries are shown separately.

Do not use:

> The entire repository is mathematically proven correct.

unless the claim has a precisely defined observation model, complete coverage, current assumptions and evidence supporting it.
