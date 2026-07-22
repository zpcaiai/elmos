---
name: java-jdk-sandbox-image-and-network-policy
description: "建立多JDK构建镜像、私服网络、资源限制、缓存和清理策略。"
---

# Image Profiles

JDK8_MAVEN
JDK11_MAVEN
JDK17_MAVEN
JDK21_MAVEN
JDK25_MAVEN
JDK21_GRADLE

## Network Profiles

NO_NETWORK
MAVEN_ONLY
APPROVED_REPOSITORIES
AGENT_PROVIDER
CUSTOM_ENTERPRISE

## Cache

依赖缓存按：

Tenant
Repository
Toolchain
Lock Hash

隔离。

## 验收标准

- 镜像具有SBOM和Digest；
- JDK版本可复现；
- 网络默认拒绝；
- 私服Credential使用tmpfs；
- Sandbox结束后Workspace清理；
- 跨租户可写缓存禁止。
