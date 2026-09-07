# Implementation Notes

- Skill ID: `project-security-observability-foundation`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 默认生成身份、权限、审计、秘密、Trace、Metric 和健康检查。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
