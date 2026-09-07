---
name: github-cloud-ghes-compatibility-contract-tests-and-release-gates
description: "Implement GitHub Cloud/GHES compatibility profiles, provider contract tests, recorded schema fixtures, real-instance smoke tests, installation/repository/ref/token/webhook/revocation tests, failure injection, and mandatory release evidence."
---

# Objective

Prove GitHub integration behavior across supported provider and API versions.

Do not claim a GHES version is supported solely because DTO deserialization
works against recorded JSON.

# Product support matrix

Initial target:

```text
GITHUB_CLOUD
REST 2026-03-10
GA

GITHUB_CLOUD
REST 2022-11-28
compatibility path

GHES 3.21
REST 2026-03-10
GA candidate after real-instance tests

GHES 3.21
REST 2022-11-28
supported compatibility

GHES 3.20
REST 2022-11-28
GA candidate

GHES 3.19
REST 2022-11-28
GA candidate

GHES 3.18
REST 2022-11-28
minimum supported candidate

GHES 3.17
transitional only while product policy permits
