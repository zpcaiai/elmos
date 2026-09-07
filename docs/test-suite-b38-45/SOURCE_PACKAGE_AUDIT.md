# Batch 38–45 source package audit

Source inspected: `/Users/stephen/Downloads/batch38-45-strict-test-suite-skills`.

- The supplied `CHECKSUMS.sha256` contains 463 entries and verified without mismatch. Its SHA-256 is `1a079d70699603ed94d53b3d6e23efb3c61b9fb79536bfb64e5d0118b010363b`.
- `FILE_MANIFEST.txt` also contains 463 entries; its SHA-256 is `4685bf6b4db413bfd739587fa1e7e5bcbd2f566e837643b440354c86bee5b775`.
- The source declared 30 Skills, 400 cases, and product Skills 1325–1496; those counts and IDs were preserved.
- All 400 supplied results were `not-run`; no source field or production evidence was upgraded to pass.

The supplied v1 gate was not certification-safe. A disposable audit fixture changed all 400 result statuses to `passed`, used SHA strings without artifact or environment files, reused one self-authored summary as all raw evidence, self-declared two customer organizations and one review, and supplied no signed request or external trust store. The source gate returned exit code 0 and `status: passed`. The v2 integration closes those paths with file-and-byte verification, exact control and case binding, identity separation, corpus independence, evidence freshness, eight domain gates, raw external evidence, and an externally trusted detached signature.
