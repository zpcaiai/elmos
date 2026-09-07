# Slightly Strict Release Gate

The package passes only when:

1. all 65 Batch test Skills have executed;
2. all 1,296 source Skills retain a direct coverage edge;
3. every Critical case passes;
4. High-severity pass rate is at least 98%;
5. overall pass rate is at least 95%;
6. Critical and High evidence completeness is 100%;
7. deterministic pass cases repeat successfully twice;
8. flaky rate is at most 1% and quarantined rate at most 0.5%;
9. no zero-tolerance or anti-fraud event occurs;
10. all waivers are owned, time-bounded, linked and non-Critical/non-High.

Critical failures are non-compensating: a high aggregate score cannot offset them.
