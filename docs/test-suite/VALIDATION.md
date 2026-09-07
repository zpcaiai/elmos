# Batch 1–37 strict test suite validation

## Structural and toolkit commands

```bash
make test-suite-check
```

This validates 52 standard Codex Skills, their 52 `agents/openai.yaml` files, the exact 408-case ownership model, all eight variants for each Batch 1–37, nine Draft 2020-12 schemas, 408 result placeholders, all templates, the deterministic installed-payload manifest, and the anti-forgery regression suite.

## Local repository qualification

```bash
make test-suite-local-qualification \
  TEST_SUITE_EVIDENCE_DIR=artifacts/test-suite/local-qualification-<timestamp>
```

The output directory is immutable: the runner refuses to overwrite an existing directory. It records an artifact manifest, environment manifest, raw logs and digests for the strict toolkit, Migration Pack Skills, Java reactor, .NET engine, Python engine, frontend client and web console. It always emits `certification_case_updates=[]`, `certification_decision=BLOCKED`, and `field_evidence_status=NOT_RUN` because local build evidence is not the 408 scenario-specific field evidence.

## Authoritative gate

```bash
python3 scripts/test-suite/run_strict_test_gate.py test-suites/batch1-37-strict
```

Without real results this command is expected to return exit code 2 and write `release-gate.json` with `decision=BLOCKED`. A certification attempt must supply all three inputs:

```bash
python3 scripts/test-suite/run_strict_test_gate.py \
  test-suites/batch1-37-strict \
  --certification-request test-suites/batch1-37-strict/certification-request.json \
  --signature test-suites/batch1-37-strict/certification-request.sig \
  --trust-store /approved/external/trust-store.json
```

The request must be signed by the independent verifier and bind the exact control digests plus all 408 result and evidence-manifest digests. The trust store must remain separate from the suite, contain the non-revoked signer key and validity interval, and match the key digest.
