# ADR 0001: 复用 rewrite-spring Recipe 底座

- 状态：已接受
- 日期：2026-07-20
- 上游快照：`ae11461b732e13c27bc7b8ed9b1b2943b8e4944f`

## 决策

通过锁定的 Maven 坐标 `org.openrewrite.recipe:rewrite-spring:6.35.0` 复用 Recipe 能力，不复制同目录仓库源码。ELMOS 的 `recipes/elmos-java-recipes` 只保存平台自己的组合 Recipe 和许可/回归测试。

## 理由

同目录底座拥有 198 个 Java 源文件及 71 个资源文件。直接复制会形成难以同步、许可边界不清的分叉；固定坐标能保留可追溯、可升级和可复现能力。

## 边界

Batch 1 只验证 Recipe 可发现性，不对客户仓库执行 Recipe。真实执行必须进入后续隔离 Workspace 批次。

