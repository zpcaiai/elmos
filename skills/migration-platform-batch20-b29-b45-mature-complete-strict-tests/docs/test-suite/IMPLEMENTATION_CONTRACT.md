# Implementation Contract

- Test executable behavior, not file presence or prose.
- Bind every result to exact commits, artifact digests, environment digest, toolchain, policy and identity.
- Use real tools and approved isolated environments; approved emulators must be documented and cannot replace required production-equivalent evidence.
- Keep development, negative, holdout and representative corpora physically and logically separate.
- Fix the product, contract or generator; never weaken tests or evidence to gain green status.
- P0 cases cannot be waived. P1 waivers require expiry, compensating controls and independent approval.
- The final gate derives status from raw case results and evidence manifests.
