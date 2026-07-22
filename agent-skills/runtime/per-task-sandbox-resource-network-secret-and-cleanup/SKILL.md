---
name: per-task-sandbox-resource-network-secret-and-cleanup
description: "为每个Repository任务建立独立受限Sandbox并执行网络、资源、文件和Secret策略。"
---

# Sandbox

## 运行模式

Rootless Container
Approved MicroVM候选
Customer-approved Local Sandbox

## 必需隔离

Read-only Root Filesystem
Ephemeral Writable Worktree
No Privileged Mode
No Host Docker Socket
CPU Limit
Memory Limit
PID Limit
Disk Quota
Timeout
Default-deny Network
Seccomp／Equivalent
Secret tmpfs
Dedicated User Namespace

## Task类型

GIT_SNAPSHOT
MAVEN_BASELINE
JAVA_HEALTH_CHECK
OPENREWRITE
MAVEN_TARGET_BUILD
VERIFICATION
DELIVERY_PREPARATION

每种Task使用类型化Command，不接受任意用户Shell。

## Network Profile

NO_NETWORK
GITHUB_CLONE_ONLY
MAVEN_APPROVED_REPOSITORIES
GITHUB_DELIVERY_ONLY
CUSTOM_ENTERPRISE_ALLOWLIST

## Secret

GitHub Token
Maven Credential
Client Certificate

规则：

- 临时注入；
- 不写入Workspace；
- 不进入Environment Dump；
- 任务结束撤销；
- 不允许子进程枚举非所需Secret。

## Cleanup

Terminate Processes
Unmount Secret
Delete Worktree
Clear Token
Seal Artifact
Verify No Residual Data

## 验收标准

- 恶意Repository不能读取宿主机文件；
- 不能访问未知域名；
- 不能获取其他任务Workspace；
- 不能挂载Docker Socket；
- 资源超限时安全终止；
- Secret不出现在日志和Artifact；
- Sandbox清理失败触发Runner Quarantine候选。
