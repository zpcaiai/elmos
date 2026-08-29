# Implementation Notes

- Skill ID: `spring-validation-exception-migration`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 迁移校验、错误码、消息、异常映射、状态码和事务回滚规则。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
