# Runbook — release-evidence-exact-artifact

1. Identify target K1–K8 owner and existing contract; do not duplicate it.
2. Apply schema/API change behind a versioned compatibility facade.
3. Run positive, denial, stale-state, replay and crash-recovery cases.
4. Confirm no authority widening and no terminal completion claim without evidence.
5. Record migration and conformance receipts.
