# Implementation Contract

- Test executable behavior, not file presence or prose.
- Bind every result to exact commits, artifact digests, environment digest, toolchain, policy and identity.
- Use real tools and approved isolated environments; approved emulators must be documented and cannot replace required production-equivalent evidence.
- Keep development, negative, holdout and representative corpora physically and logically separate.
- Fix the product, contract or generator; never weaken tests or evidence to gain green status.
- P0 cases cannot be waived. P1 waivers require expiry, compensating controls and independent approval.
- The final gate derives status from raw case results and evidence manifests.
- A passed result binds the canonical case/catalog digest, exact artifact and environment files, all required evidence roles, replay command, executor, independent verifier and authorization references.
- Holdout and representative corpora use distinct digests, remain unavailable to product-fix authoring, and carry independent attestations.
- Certification requires one externally trusted signed request that binds the exact 408 result files and their evidence-manifest digests. The trust store is separate from the suite and revocation is fail-closed.
- Local repository builds are engineering qualification only. They never mutate certification results or convert `not-run` / `NOT_RUN` into pass.
