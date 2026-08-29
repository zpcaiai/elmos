# Limitations and Honest Claims

This archive is an implementation-grade **Skills package** with schemas, route profiles, policies, validators, templates, examples, and a CLI. It does not contain a finished compiler, complete production adapters, or verified conversions for every route.

Static validation can prove:

- package structure and internal consistency
- Skill inventory and required sections
- dependency acyclicity
- route and technology registry consistency
- schema syntax
- installer behavior
- archive integrity and checksums

Static validation cannot prove:

- parser or compiler correctness
- semantic equivalence of a converted system
- production safety
- security certification
- route maturity
- framework/version compatibility
- performance equivalence
- successful migration of a particular customer workload

Those claims require implementing the Skills in an ELMOS codebase and producing current execution evidence.
