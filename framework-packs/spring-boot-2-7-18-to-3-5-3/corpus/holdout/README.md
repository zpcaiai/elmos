# Holdout corpus

One non-customer public holdout was executed as local engineering evidence:

- Repository: `https://github.com/gvogi/grade-submission.git`
- Commit: `a4c48b1dddb8a320c11ee05bdadefc53df74b3a4`
- Snapshot SHA-256: `616fcc5000da1fb38abf778a9f4ceb532d9df88c17c838cd9f062b7702ad12fd`
- Migration Run: `8377ccbc-3fb9-4ca6-b574-020abe5fa47a`
- Result: source 1/1 and target 1/1 tests passed; independent verifier `PASS`
- Artifact SHA-256: `5dc0572061350a1df2d5b7bb434d41abd4a01bb9df83f86c73aa3b8318b15427`

This directory is independent of the development and representative corpora. The repository was
not used to tune the recipe or deterministic repair logic. It is not a customer holdout and does
not satisfy customer acceptance or external certification evidence.
