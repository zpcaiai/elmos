# Implementation Notes

- Skill ID: `spring-transaction-persistence-migration`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 迁移 JDBC、Hibernate、MyBatis、事务传播、锁和 Lazy 语义。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
