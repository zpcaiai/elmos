# Batch 30 Framework Version Policy

1. Certification applies to an exact tuple: source framework/runtime/build/provider versions plus target framework/runtime/build/provider versions.
2. Do not use `latest`, mutable image tags, unbounded semantic ranges, or undocumented defaults in a certified pack.
3. Group versions only when executable evidence proves no material framework-contract difference inside the band.
4. Each tuple has a lifecycle state: research, preview, stable, LTS, maintenance, deprecated, EOL, or blocked.
5. A provider upgrade can invalidate certification even when the framework version is unchanged.
6. Security fixes may be backported only to funded maintenance/LTS tuples.
7. Deprecation requires notice, migration guidance, customer impact, and an end-of-support date.
8. Long-running workflows and private installations must retain the exact pack/profile/toolchain artifacts required for replay.
9. Version evidence must be regenerated when defaults, serializers, DI, security, ORM, broker, cache, scheduler, or runtime lifecycle change.
10. Support matrices are claims; they must link executable evidence for every certified capability.
