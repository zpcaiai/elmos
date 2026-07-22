---
name: mainframe-test-generation-semantic-equivalence-and-validation
description: Build replayable COBOL, CICS, IMS, batch, Db2, VSAM, file, and 3270 baselines; generate governed tests; and compare original and modernized behavior, side effects, data states, errors, performance, and test counts. Use for semantic-equivalence or regression evidence.
---

# Mainframe Semantic Validation

## Build the baseline

1. Freeze copybook input, COMMAREA or containers, IMS message, Db2/VSAM state, batch datasets, JCL parameters, screen actions, source/load module, and environment.
2. Capture return code, output layout, RESP/RESP2, IMS status, SQLCODE, database and file state, messages, control totals, spool, abend, screen, and performance.
3. Normalize comparisons only through explicit exact, field, numeric-tolerance, order, business-equivalent, expected-difference, or not-comparable rules.
4. Test packed decimal sign, scale, precision, invalid digit, overflow, rounding, and negative zero separately.
5. Reconcile generated, discovered, executed, passed, failed, skipped, and unsupported test counts.

## Judge independently

- Run original and target with the same inputs and data snapshot.
- Compare all side effects and final state; compilation or structural similarity is insufficient.
- Keep generated tests review-only until they fail before the fix or prove effectiveness through mutation or an equivalent independent check.
