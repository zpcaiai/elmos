# Implementation Notes

- Skill ID: `tool-and-mcp-supply-chain-trust`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 校验第三方 Tool/MCP 的来源、权限、更新、依赖和返回内容。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
