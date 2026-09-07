# Implementation Notes

- Skill ID: `domain-proof-and-certification-pack`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 为每条业务线维护专用不变量、反例、证据模板和 E0-E5 门。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
