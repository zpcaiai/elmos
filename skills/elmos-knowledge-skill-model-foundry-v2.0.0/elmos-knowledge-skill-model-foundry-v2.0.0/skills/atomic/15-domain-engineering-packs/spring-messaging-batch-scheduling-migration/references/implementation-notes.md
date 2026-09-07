# Implementation Notes

- Skill ID: `spring-messaging-batch-scheduling-migration`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P1`
- Capability: 迁移消息、定时、批处理、重试、幂等和死信行为。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
