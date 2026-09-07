---
name: per-task-sandbox-resource-network-secret-and-cache-isolation
description: "为每项Clone、Build、OpenRewrite和Agent任务建立独立OS级Sandbox和本地安全Policy。"
---

# Sandbox Provider

接口：

SandboxProvider
- create
- mountWorkspace
- injectSecretReference
- configureNetwork
- execute
- cancel
- collect
- destroy

MVP Linux Provider：

Rootless Podman
或
Rootless containerd兼容实现

## Sandbox约束

Rootless
Read-only Root Filesystem
Drop All Capabilities
No New Privileges
Seccomp
AppArmor／SELinux候选
PID Limit
CPU Limit
Memory Limit
Disk Quota
Timeout
Dedicated Network Namespace
No Host Docker Socket
No Privileged Mode

## Workspace

/source
只读Snapshot

/work
可写Worktree

/output
允许导出的Artifact

/secrets
tmpfs，只对启动进程可见

/cache
受Tenant和Toolchain隔离

## Network

NO_NETWORK
SCM_ONLY
MAVEN_REPOSITORY_ONLY
AGENT_PROVIDER_ONLY
CUSTOM_ALLOWLIST

使用Egress Proxy或明确IP／域名Policy。

DNS Rebinding和Redirect必须重新验证目标。

## Secret

Secret Broker向Runner返回：

Secret Lease
Target Process
Mount Path
Expiry
Allowed Command

Secret不得进入：

Environment Dump
Build Log
Agent Context
Workspace
Patch
Artifact

## Cache

Cache Key：

Tenant
Repository
Toolchain
JDK
Wrapper Hash
Lock／POM Hash
Network Profile

禁止跨Tenant可写Cache。

## Command

Runner执行类型化Command：

GIT_CLONE
MAVEN_BUILD
OPENREWRITE_DRY_RUN
OPENREWRITE_APPLY
AGENT_REPAIR

不暴露：

RUN_ARBITRARY_SHELL

## 验收标准

- 每任务使用全新Sandbox；
- Repository脚本不能访问宿主机；
- 默认无网络；
- Agent不能读取Secret；
- 任务取消后全部子进程终止；
- Disk／CPU／Memory超限安全失败；
- Sandbox销毁后源码不可读取；
- 逃逸和网络攻击测试进入CI。
