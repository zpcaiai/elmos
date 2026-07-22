# Batch 38–45 evidence and anti-forgery contract

Every passed case binds the canonical case and catalog digests, exact artifact and environment files, immutable raw evidence with byte counts and SHA-256 digests, execution interval, replay command, authorization, executor, and an independent verifier. Development, holdout, and representative corpora must use different manifests and digests; holdout and representative data deny authoring access and carry independent attestations.

Certification requires one fresh detached RSA-SHA256 signature over a request that binds all 400 result digests, their evidence-manifest digests, the immutable control digests, the release-evidence control, eight M38–M45 domain gate results, two distinct customer organizations, and an independent review. The trust store is supplied outside the suite, contains a non-revoked authorized signer, and binds the public-key digest.

Forbidden shortcuts include status editing, placeholder digests, path escape, stale or future evidence, self-verification, reused holdout/representative corpora, summary-only customer evidence, an in-suite trust anchor, deleted failures, automatic Golden updates, broadened permissions, widened tolerances, mocked production claims, unsigned requests, or a signature that does not bind the exact 400-case set.

Local structural validation and synthetic signed fixtures are gate-engineering evidence only. They never change checked-in case results from `not-run` or field evidence from `NOT_RUN`.
