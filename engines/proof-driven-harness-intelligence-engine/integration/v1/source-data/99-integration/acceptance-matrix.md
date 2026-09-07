# Acceptance Matrix

| Capability family | Minimum automated acceptance |
|---|---|
| Semantic graph | symbol/reference fixtures + incremental refresh + unresolved-edge reporting |
| Transactional edit | stale rejection + rollback + postcondition failure recovery |
| Runtime proof | reproducible source/target scenario + normalized behavioral diff |
| Agent isolation | concurrent write workers + stale lease/fence rejection |
| Structured yield | malformed result rejected + schema version migration |
| Advisor | blocker/concern/nit routing + dedupe + failure isolation + quarantine |
| Policy | conflict explanation + semantic trigger + blocker evidence |
| Durable runtime | process crash/restart in every phase + no duplicated side effects |
| Model routing | fallback under quota/429 + effort ceiling preserved |
| Context | compaction/rewind/resume without loss of required invariants |
| Skill evolution | candidate cannot promote without corpus/gate evidence |
| Certification | insufficient evidence cannot become pass |
