# Package and Platform Acceptance Tests

## Static package acceptance

- 64 unique Skill IDs and names
- every manifest path exists
- each Skill has YAML frontmatter and required sections
- 14 exact technology IDs
- 196 route-matrix cells
- 18 reference route profiles
- dependency graph is acyclic
- all JSON schemas parse
- default readiness is `not-run`
- obvious secret patterns are absent
- installer clean-copy test passes
- ZIP and TAR.GZ integrity and checksums pass

## Platform implementation acceptance

Static package acceptance does not satisfy these tests:

1. Submit a run, disconnect the client, terminate a worker, resume, and retrieve artifacts.
2. Deny an unauthorized command, path, network destination, and secret request.
3. Build a representative source fixture with the discovered native toolchain.
4. Generate valid Project, Semantic, and Framework IR with provenance.
5. Execute a deterministic codemod twice and observe no second diff.
6. Reject an unrelated or over-budget agent patch.
7. Compile a representative target.
8. Detect injected API, data, concurrency, timezone, and security regressions.
9. Roll back a canary or simulated data migration.
10. Invalidate readiness when source, dependency, toolchain, test, rule, or policy changes.
