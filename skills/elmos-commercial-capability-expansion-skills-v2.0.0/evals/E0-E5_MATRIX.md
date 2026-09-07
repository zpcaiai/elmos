# E0-E5 Evidence Matrix

Elmos can preserve its E0-E5 external certification language while composing finer internal gates.

| Level | Minimum meaning | Typical mandatory evidence |
|---|---|---|
| E0 | Parse/plan integrity | repository discovery, parse/index success, unsupported construct inventory |
| E1 | Build correctness | target build, dependency lock, static checks, deterministic edit validation |
| E2 | Functional correctness | unit/integration/property tests, affected-test closure |
| E3 | Behavioral equivalence | differential runtime, API/contract tests, DB reconciliation, browser E2E as applicable |
| E4 | Robustness/security | fuzz, taint/dataflow, vulnerability/SBOM, sandbox and policy evidence, fault injection where relevant |
| E5 | Production certification | performance/SLO, native runtime lab, provenance/signatures, rollback, canary/shadow evidence, optional formal proof for critical invariants |

A route may add mandatory sub-gates; it may not silently redefine a higher level to mean less evidence than its route policy requires.
