# Implementation Notes

- Skill ID: `frontend-platform-api-and-miniapp-targets`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 适配微信、支付宝、抖音、小红书小程序及平台权限和限制。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
