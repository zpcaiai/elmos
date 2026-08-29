# Technology Adapter Contract

Every adapter must expose:

1. detection of files, build roots, versions, frameworks, generated and vendored code;
2. native toolchain resolution;
3. parser and symbol/type resolution;
4. Project/Semantic/Framework IR emission;
5. unsupported-construct and semantic-loss diagnostics;
6. deterministic source emission or patch application where supported;
7. build and test command generation;
8. fixture and version compatibility metadata;
9. evidence producer metadata;
10. cancellation and bounded resource behavior.

Adapter APIs must accept snapshot and policy references, not arbitrary host paths. Parser versions and configuration are part of IR identity.
