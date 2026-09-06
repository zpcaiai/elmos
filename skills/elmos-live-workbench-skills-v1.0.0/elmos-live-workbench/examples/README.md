# Examples are data-shape examples, NOT deployment evidence

`source-anchor.json` binds to the original bundled Python bytes. The two cart implementations
were authored as educational fixtures, not produced by a real Elmos converter.
`reports/native-fixtures.json` and `reports/debugpy-lab.json` contain actual local observations.
The event, delivery, readiness, cleanup and command envelopes here are ILLUSTRATIVE: their
IDs, times, commit status and signatures do not establish a real host commit, running sandbox,
cleanup or authenticated deployment. Never publish these examples as real attestation.
Production paths must reject example issuers, unverified signatures and unresolved image digests.
