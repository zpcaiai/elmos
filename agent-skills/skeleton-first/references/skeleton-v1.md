# Skeleton-first operating contract

Batch 4 consumes only modules eligible for skeleton generation. It selects a target profile and evidenced stack, maps every source module/declaration/test, then emits deterministic target repository structure, build files, signatures, contracts, pending tests, configuration/resource placeholders, and source-target mappings. It does not translate business method bodies, framework internals, ORM queries, transactions, authorization, or test bodies.

Hard constraints outrank preferences; unresolved target runtime, dependency-policy conflicts, name collisions, broken mappings, unsafe resources, or unsupported contracts block. Never invent dependency versions, copy secrets/vendor/binaries, silently rename public external fields, downgrade async/error/resource semantics, return misleading safe defaults, or mark placeholder tests passed. Generated and manual regions stay separate; identical regeneration has no diff and unknown manual content is never overwritten.

Build evidence comes from an isolated approved runner. Build-model load, dependency resolution, syntax compile, and test discovery are distinct; test discovery does not execute business tests. Apply S-A/S-B structural and contract coverage, S-C build/compile/discovery and zero blockers, and S-D higher automation thresholds per module. Skeleton existence is not implementation completion.
