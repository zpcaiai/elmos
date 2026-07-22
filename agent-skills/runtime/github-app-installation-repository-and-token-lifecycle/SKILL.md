---
name: github-app-installation-repository-and-token-lifecycle
description: "管理GitHub App安装、Repository授权、短期Token、权限收窄、暂停、撤销和Enterprise兼容。"
---

# GitHub Installation

## 对象

GitHub App
Installation
Installation Account
Installation Repository
Installation Permission
Installation State
API Compatibility Profile

## Installation状态

PENDING
ACTIVE
SUSPENDED
DELETED
ACCESS_REDUCED
SYNC_FAILED

## Repository同步

来源：

- installation webhook；
- installation_repositories webhook；
- GitHub REST reconciliation；
- 手工Admin Refresh。

记录：

GitHub Repository ID
Owner
Name
Visibility
Default Branch
Archived
Installation ID
Granted At
Removed At

## Token类型

APP_JWT
用于请求Installation Token

CLONE_TOKEN
只允许Contents Read

DELIVERY_TOKEN
允许Contents Write、Pull Requests Write

CHECK_TOKEN
允许Checks Write

不同用途必须独立签发。

## Token Broker

输入：

Tenant
Installation
Repository
Purpose
Requested Permissions
TTL

输出：

短期Token
Expiry
Granted Repositories
Granted Permissions
Token Reference

Token不得写入：

Database
Log
Artifact
Workflow Payload
Agent Prompt

## 访问撤销

收到：

Installation Suspended
Repository Removed
Installation Deleted

必须：

- 停止签发新Token；
- 取消未开始任务；
- 通知活动Runner；
- 标记现有Snapshot来源状态；
- 保留历史Evidence。

## Enterprise

保存：

Provider Type
Base URL
REST API Version
GitHub Enterprise Server Version
Supported Endpoint Matrix

## 错误代码

GITHUB_INSTALLATION_NOT_FOUND
GITHUB_INSTALLATION_SUSPENDED
GITHUB_REPOSITORY_NOT_GRANTED
GITHUB_PERMISSION_INSUFFICIENT
GITHUB_TOKEN_SCOPE_MISMATCH
GITHUB_API_VERSION_UNSUPPORTED

## 验收标准

- Token按Repository和Purpose收窄；
- Token不持久化；
- Repository移除后无法再次Clone；
- Installation暂停后新任务被拒绝；
- Token格式不依赖固定长度；
- Clone和Delivery使用不同权限；
- GitHub Enterprise兼容按版本验证。
