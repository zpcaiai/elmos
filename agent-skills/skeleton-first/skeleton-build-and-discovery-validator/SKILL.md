---
name: skeleton-build-and-discovery-validator
description: Validate build-model loading, allowed dependency resolution, syntax compilation, and test discovery in isolation. Use before skeleton quality gates.
---
# Skeleton Build and Discovery Validator
Read `../references/skeleton-v1.md`. In an approved sandbox, separately record build load, dependency resolution, syntax/signature/generic compile, and test discovery under strict/provisional/offline modes. Do not execute business tests or placeholder side effects, fetch unapproved public dependencies, ignore failures, or equate discovery with passing. Bind logs/environment/toolchain/errors/fixes to generation ID and keep deterministic repair bounded.
