---
name: runner-fleet-cache-concurrency-and-build-performance-optimizer
description: 治理Hosted、Self-hosted和Private Runner的隔离、容量、缓存、队列、性能和成本。
---

# Runner Fleet

## Runner类型

HOSTED
SELF_HOSTED_EPHEMERAL
SELF_HOSTED_PERSISTENT
PRIVATE_RUNNER
GPU
WINDOWS
MACOS
MAINFRAME
HIGH_MEMORY
AIR_GAPPED

## Runner Capability

OS
Architecture
CPU
Memory
GPU
Network
Region
Toolchain
Security Profile
Tenant
Cost

## 隔离

SHARED_EPHEMERAL
TENANT_DEDICATED
JOB_DEDICATED
PERSISTENT_TRUSTED
UNTRUSTED_CODE_SANDBOX

不受信任PR不应运行于长期、含Credential的Persistent Runner。

## Queue

记录：

- Queue Time；
- Execution Time；
- Priority；
- Cancellation；
- Starvation；
- Capacity；
- Cost。

## Cache类型

DEPENDENCY
BUILD
CONTAINER_LAYER
TEST
REMOTE_EXECUTION
ARTIFACT

## Cache Key

必须绑定：

- Dependency Lock；
- Toolchain；
- OS；
- Architecture；
- Build Config；
- Security Scope。

## Cache安全

检测：

CACHE_POISONING
CROSS_TENANT_CACHE
SECRET_IN_CACHE
UNVERIFIED_CACHE
STALE_CACHE

## Concurrency

- Repository；
- Branch；
- Environment；
- Deployment；
- Resource；
- Tenant；
- Platform Quota。

## 优化

- Changed-module Build；
- Remote Cache；
- Test Impact；
- Parallel Test；
- Artifact Reuse；
- Prebuilt Toolchain；
- Warm Image；
- Runner Autoscaling。

## 验收标准

- Runner Capability明确；
- 不受信任代码隔离；
- Queue和执行时间分开；
- Cache Key完整；
- 跨租户Cache禁止；
- 优化不跳过质量Gate；
- 成本和性能同时衡量。
