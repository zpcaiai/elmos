# Implementation Notes

- Skill ID: `spring-shadow-differential-golden-route`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 通过影子流量、差分、回滚和真实大型仓库形成可付费 Golden Route。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
