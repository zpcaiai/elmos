---
name: test-impact-selection-prioritization-and-parallel-execution
description: Select, explain, prioritize, shard, and safely parallelize tests using code, dependency, contract, schema, infrastructure, runtime, history, and risk graphs. Use for pull-request acceleration or trustworthy incremental test execution.
---

# Test Impact, Selection, and Parallel Execution

## Build the impact graph

Combine changed files/symbols, dependency and call graphs, contracts, data schemas, infrastructure, runtime traces, historical coverage/failures, defect history, and risk. Record direct-symbol, transitive-call, contract, database, message, configuration, infrastructure, runtime-observed, historical-failure, and owner-declared edges with graph versions.

## Select conservatively

Classify tests as mandatory, high-priority, recommended, optional, not impacted, or unknown. Expand critical scope when analysis is unknown; never convert unknown to not impacted. Explain why every test was selected or omitted, including graph and risk versions.

## Stage execution

For pull requests run changed unit, related component, contract, critical smoke, and selected mutation tests. Add integration, cross-module, wider mutation, and selected E2E at merge. Run full, property, mutation, performance, resilience, and long-running suites on scheduled stages.

## Shard safely

Use historical duration, resource needs, framework, environment, isolation, data, and serial constraints. Mark parallel-safe, class-parallel, serial-resource, serial-suite, or unknown. Allocate unique ports and namespaces. If fail-fast stops work, preserve the unexecuted list, reason, coverage gap, and full-run requirement; unexecuted is never pass.
