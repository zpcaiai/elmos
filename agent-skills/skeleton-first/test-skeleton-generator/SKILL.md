---
name: test-skeleton-generator
description: Generate mapped target test projects and pending unit/integration/contract/differential/security/performance skeletons. Use from source tests, APIs, and obligations.
---
# Test Skeleton Generator
Read `../references/skeleton-v1.md`. Map every source test and blocking obligation to a target test/manual strategy; generate fixtures, lifecycle, inputs/expected placeholders, source/obligation links and differential adapters. Pending tests must fail, skip, or throw with a reason—never `assert true` or pass. Separate test dependencies, preserve deleted-test proof, and keep discovery distinct from execution.
