# Package Validation Report

Package: `elmos-build-cache-staging-codex-claude-parity`  
Version: `1.2.0`  
Date: `2026-08-20`

## Final checks required by `./validate.sh`

- Skill count: **42**
- v1.1.0 Skills retained: **31**
- New coding-agent cache parity Skills: **11**
- Dependency references and topological DAG: valid
- Skill frontmatter package/version/required sections: valid
- Entry Skill: `elmos-codex-claude-cache-parity-rollout`
- Required package files: present
- JSON files and JSON Schemas: syntactically valid
- Python implementation/scripts: compile successfully
- Reference unit tests: **34 expected**
- Example parity gate: mandatory pass with **15 checks**
- Installer custom-destination smoke test: **42 Skills expected**
- Internal SHA-256 manifest: must match final frozen contents

## Reference behaviors covered

Existing v1.1.0 coverage remains: canonical ActionKeys, CAS integrity/corruption detection, staging lifecycle, path/lease safety, recovery planning, complete-tree publication, SIEVE, S3-FIFO, W-TinyLFU, GDSF, equal-capacity replay, DAG prefetch, and cost-aware metrics.

v1.2.0 adds tests for:

- canonical stable prompt prefix independent of map order and volatile turn data;
- stable-to-volatile segment ordering enforcement;
- provider/model/effort/tool/prefix affinity identity;
- normalized cached-token reuse accounting;
- append-only context event idempotency, staleness/reread, hash-chain mutation detection;
- environment snapshot key stability and secret-reference invalidation;
- restore-versus-rebuild bypass;
- compatibility-safe affinity scoring;
- first-difference miss classification;
- compute-weighted reuse;
- all default parity thresholds;
- zero-tolerance false-hit rejection.

## Scope note

The reference fixture demonstrates contracts and gates. It is not a production ELMOS benchmark. Actual parity requires implementation in the ELMOS repository and a fresh certificate bound to the exact release candidate, provider profiles, corpus, and platform.
