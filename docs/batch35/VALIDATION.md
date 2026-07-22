# Validation Commands

```bash
make -f Makefile.batch35 batch35-check
make -f Makefile.batch35 batch35-local-rehearsal
/opt/homebrew/bin/uv run --quiet --with jsonschema --with pyyaml python \
  scripts/batch35/validate_verification_pack.py verification-packs/<pack-key>
/opt/homebrew/bin/uv run --quiet --with jsonschema --with pyyaml python \
  scripts/batch35/run_verification_gate.py verification-packs/<pack-key>
```

`gate-result.json` reports the structural result separately from `certification_decision`. A research, experimental, or limited pack can pass structural validation only as `NOT_CERTIFIED`. Certification requires immutable `passed` manifests for negative, holdout, and representative corpora, evidence digests and resolvable references, all thresholds, zero-tolerance checks, fully supported assurance claims, and approvals.
