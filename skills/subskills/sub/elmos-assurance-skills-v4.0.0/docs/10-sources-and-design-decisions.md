# 来源与设计决策

核验日期：2026-09-09。下列来源支持工具能力/接口语义；本包架构、门槛与产品设计是本次建议，不代表这些项目替Elmos背书。

| ID | 一手来源 | 用途与边界 |
|---|---|---|
| S01 | https://agentskills.io/specification | SKILL.md frontmatter、渐进加载、资源组织 |
| S02 | https://developers.openai.com/codex/skills | 官方重定向至ChatGPT Learn，Codex .agents/skills本地发现 |
| S03 | https://spec.openapis.org/oas/v3.1.1.html | 本包选择3.1.1作为参考HTTP合同互操作基线 |
| S04 | https://spec.openapis.org/oas/v3.2.0.html | 已有3.2，不假称3.1最新；迁移需adapter兼容测试 |
| S05 | https://schemathesis.readthedocs.io/ | OpenAPI/GraphQL性质及stateful测试，非完整业务Oracle |
| S06 | https://lean-lang.org/doc/reference/latest/ValidatingProofs/ | 公理检查、trusted challenge、comparator、外部checker与残余信任 |
| S07 | https://github.com/leanprover/lean4/releases | 当前可见v4.33.1，非宣称本机已运行 |
| S08 | https://sqlglot.com/ | 解析/transpile适配器候选，非语义认证器 |
| S09 | https://github.com/sqlancer/sqlancer | DBMS测试oracle启发；不能单独认证跨dialect转换 |
| S10 | https://pitest.org/quickstart/basic_concepts/ | mutation、equivalent mutants；须正确处理分母 |
| S11 | https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html | proxy/self-invocation风险需真实框架测试 |
| S12 | https://docs.sigstore.dev/cosign/verifying/attestation/ | in-toto/DSSE签署验证；签名不等于正确性 |
| S13 | https://slsa.dev/spec/v1.2/build-provenance | artifact digest/provenance字段设计；不宣称SLSA认证 |
| S14 | https://docs.tlapl.us/using%3Atlc%3Astart | 有限模型边界；不把bounded通过当无限证明 |

## 继承的用户资料

Library中的 `ELMOS_ROUTER_SKILL_PACKAGE.md`：Elmos持有语义路由、ModelExecutionPlan、权限与结果commit；网关可替换。
`SKILL_INDEX(20260828-095237).md`与`SKILL_INDEX(20260828-104455).md`：独立K8、scope compiler、holdout、版本绑定、原16 routes约定。
只复用这些可见设计约定；没有读取实际Elmos源代码，不声称这些能力已实现。

## ADR摘要

A01：横切assurance扩展，不增业务线/重写Harness。
A02：冻结scope+oracle+obligations，拒绝自动缩分母。
A03：规范正确性与历史兼容性分开。
A04：Ethen是角色/身份/信任域，不是模型昵称即外部认证。
A05：Lean承担可表达的critical claims，必须绑定实际artifact。
A06：物理效应at-least-once+幂等/对账；不泛化exactly-once。
A07：参考内核不能生产签发；正式签署复用K8/KMS。
A08：最新文档不等于已验证依赖；生产锁定精确工具链。
