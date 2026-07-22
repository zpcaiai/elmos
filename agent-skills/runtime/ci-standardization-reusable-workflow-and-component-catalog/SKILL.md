---
name: ci-standardization-reusable-workflow-and-component-catalog
description: 将复制粘贴式流水线转为版本化、可测试、可组合的Reusable Workflow和Pipeline Component。
---

# CI Standardization

## Pipeline Component类型

SOURCE_CHECKOUT
BUILD
TEST
SECURITY
PACKAGE
SBOM
SIGN
PUBLISH
DEPLOY
VERIFY
PROMOTE
ROLLBACK
NOTIFY

## Component Contract

{
  "componentId": "java-build",
  "version": "2.4.0",
  "inputs": [],
  "outputs": [],
  "permissions": [],
  "artifactTypes": [],
  "supportedRunners": []
}

## Golden Pipeline

Repository只声明：

- Workload类型；
- Runtime；
- Build命令；
- Test Profile；
- Artifact；
- Deployment Profile。

平台决定：

- Runner；
- Security；
- Cache；
- Provenance；
- Promotion；
- Evidence。

## Version引用

PINNED_DIGEST
PINNED_COMMIT
PINNED_RELEASE
FLOATING_CHANNEL
BRANCH
LATEST

生产路径默认：
