# proof-driven-harness-v3-local

Deterministically generated Batch 35 local verification pack for the exact proof-driven harness v3.0 base and v3.1 runtime-assurance delta qualification receipts for composite artifact 3.1.0. Only development and negative local corpora are passed. All holdout, representative, external, independent, production, and certification evidence remains `NOT_RUN` or `NOT_CERTIFIED`.

Run structural validation and the conservative gate:

```sh
python3 scripts/batch35/validate_verification_pack.py verification-packs/proof-driven-harness-v3-local
python3 scripts/batch35/run_verification_gate.py verification-packs/proof-driven-harness-v3-local
```

For this canonical `limited` pack, gate exit code 0 means the gate evaluation executed successfully. It does not mean certification passed. The authoritative machine fields remain `certification_decision=NOT_CERTIFIED` and `certification_readiness=BLOCKED` until the named external obligations exist. A temporary certification-request copy is used only as a negative test and is never published.
