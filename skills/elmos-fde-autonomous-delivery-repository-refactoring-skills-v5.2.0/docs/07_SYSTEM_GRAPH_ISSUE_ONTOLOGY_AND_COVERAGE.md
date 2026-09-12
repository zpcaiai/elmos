# 07 — System Graph, Issue Ontology and Coverage

## System Graph layers

Syntax/type; control/call/data/taint/exception; state/transaction/effect; module/service/API/event/database; identity/permission/trust; infrastructure/deployment; test/runtime/trace; Git ownership/change coupling; business capability/rule/workflow. Dynamic and uncertain edges retain confidence and alternate explanations.

## Issue domains

| Domain | Types | Examples |
|---|---|---|
| business-correctness | 8 | missing business rule, conflicting rule, illegal state transition, unhandled exception path … |
| functional-correctness | 8 | nullability defect, boundary-condition defect, incorrect error semantics, resource leak … |
| architecture | 8 | cyclic dependency, layer violation, wrong module boundary, shared database coupling … |
| maintainability | 9 | duplicate implementation, god object, long function, high cognitive complexity … |
| concurrency-distributed | 10 | race condition, deadlock, lost update, duplicate side effect … |
| transaction-consistency | 8 | incorrect transaction boundary, cross-service transaction coupling, missing compensation, cache/database inconsistency … |
| security | 12 | authentication weakness, authorization bypass, tenant escape, injection … |
| privacy-compliance | 9 | excessive data collection, missing purpose limitation, residency violation, retention violation … |
| dependency-supply-chain | 10 | known vulnerability, abandoned dependency, version conflict, license conflict … |
| api-integration | 9 | contract drift, breaking change, ambiguous error code, missing timeout … |
| database-data | 10 | schema integrity defect, missing or harmful index, N+1 query, slow query … |
| performance-capacity | 10 | algorithmic bottleneck, memory leak, GC pressure, lock contention … |
| reliability-resilience | 9 | single point of failure, missing degradation, missing circuit breaker, invalid retry budget … |
| observability-operations | 10 | trace gap, metric gap, uncorrelated logs, alert noise … |
| testing-quality | 11 | critical path untested, weak oracle, flaky test, test pollution … |
| ci-cd-developer-experience | 10 | non-reproducible build, slow feedback, unsafe release gate, manual deployment … |
| frontend-ux-accessibility | 9 | critical journey friction, state inconsistency, navigation defect, accessibility violation … |
| i18n-mobile-platform | 9 | locale formatting defect, translation key drift, RTL defect, timezone mismatch … |
| ai-agent | 11 | prompt injection, tool overreach, hallucinated action, untraceable decision … |
| cost-finops-sustainability | 10 | idle resource, cost anomaly, unbounded token usage, inefficient model routing … |
| documentation-knowledge-governance | 10 | documentation drift, missing ADR, tribal knowledge, bus-factor risk … |

## Finding quality

A Finding requires exact location, evidence, trigger/reproduction, affected capability, severity, likelihood, blast radius, business impact, confidence, false-positive risk, root cause, options, recommended remediation, verification, rollback, automation level and approvals. Tool-native output remains available for audit.

## Coverage truth

No generic score may hide unknowns. Coverage is reported per component, technology, issue domain, analysis method and critical journey as observed/detected, verified absent, unknown or unsupported.
