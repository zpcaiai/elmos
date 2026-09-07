---
id: elmos-java-legacy-web-repository-modernization
title: Elmos Java Legacy Web Repository Modernization
version: 1.0.0
priority: P0
entrypoint: skills/control-plane/00-modernization-orchestrator/SKILL.md
---

# Elmos Java Legacy Web Repository Modernization

## 任务定义

将 Struts 1、Struts 2、Servlet/JSP 或混合式 Java Web 仓库迁移到 Spring Boot 4，并满足：

```text
repository-level semantic preservation
+ behavioral equivalence
+ evidence-backed production certification
```

## 必须调用的阶段

1. `control-plane`
2. `repository-forensics`
3. `semantic-recovery`
4. `semantic-model`
5. `planning`
6. `transformation`
7. `verification`
8. `repair-certification`

除非任务契约明确只要求 scan/model/plan，否则不得跳过验证；只有用户明确要求代码草案时，才允许停在 E2 之前。

## 全局硬规则

- 目标基线：Spring Boot 4.x / Spring Framework 7.x / Jakarta EE 11 / Servlet 6.1。
- Java 最低 17，默认 21；JDK 升级风险与框架迁移风险分别建模。
- JSP 默认 preserve-first；保留 JSP 时由 planner 决定 WAR/容器方案。
- 不允许 regex-only 的 javax→jakarta 或框架替换。
- 所有生成必须消费 Semantic IR；不得由 generator 再次随意解释 legacy 仓库。
- 所有目标节点必须进入 semantic source map。
- 行为差分覆盖 HTTP、view、session、DB、transaction、security、side effects、concurrency。
- normalizer 必须显式、版本化且不能掩盖业务差异。
- critical unknown 或关键行为差异阻断 E5。
- 每个长任务必须可暂停、恢复、取消、回滚，并报告机器 wall-clock ETA。

## 入口算法

```text
resolve contract & authority
snapshot repository and environment
recover effective build/runtime/route topology
run framework-specific semantic adapters
merge evidence graph
normalize semantic IR
mine behavioral contracts and unknowns
score semantic risk
plan target architecture and conversion waves
apply deterministic change sets
build and run target
execute differential verification
classify mismatches
bounded auto-repair + impact regression
assemble evidence bundle
issue E0–E5 result
execute canary/cutover only when authorized
```

## 输出

最低输出集：

```text
repository-snapshot/
repository-evidence-graph.json
legacy-web-semantic-ir.json
unknown-semantics-ledger.yaml
semantic-risk-register.yaml
migration-plan.yaml
target-repository/
semantic-source-map.json
verification/
repair-ledger/
cutover-plan.yaml
certification-bundle.json
```

## 禁止的成功声明

不得仅凭以下条件宣称迁移成功：

- 所有源文件已生成；
- Maven/Gradle compile 成功；
- Spring Boot 启动成功；
- 单元测试成功；
- 少量 HTTP smoke test 成功；
- 模型认为“看起来等价”。

成功等级必须使用 E0–E5。
