# Threat Model

## Assets

Customer source, formulas, models, counterexamples, database fixtures, proof certificates, billing events, TCB manifests, release decisions and waivers.

## Adversaries and failures

- malicious repository content targeting parsers or solver runners;
- prompt/tool injection attempting to relax proof policy;
- compromised verifier image or output parser;
- tenant attempting cross-tenant artifact/cache access;
- stale worker committing after lease loss;
- operator inflating bounded/unknown results;
- forged or mutated evidence;
- denial of service through pathologically hard formulas;
- leakage through logs, traces or counterexamples;
- dependency or semantic-model drift after certification.

## Controls

- no-network, no-secret, non-root, read-only-root solver sandboxes;
- parser limits and untrusted input isolation;
- tenant-scoped RLS and encryption;
- content-addressed immutable evidence;
- lease/fencing and terminal-state guards;
- canonical proof status schema and Rego anti-inflation policy;
- exact image digest, SBOM, signature and provenance;
- formula size, timeout, CPU, memory and credit budgets;
- structured redaction and no source formulas in metric labels;
- drift monitor and automatic gate reevaluation;
- four-eyes, expiring waivers.

## Residual risks

SMT solver soundness, semantic-adapter bugs, incomplete environment models, vendor database deviations, and unmodeled native/dynamic behavior remain possible. They are recorded in the TCB or Assumption Ledger and addressed through cross-checking, differential tests and runtime monitors.
