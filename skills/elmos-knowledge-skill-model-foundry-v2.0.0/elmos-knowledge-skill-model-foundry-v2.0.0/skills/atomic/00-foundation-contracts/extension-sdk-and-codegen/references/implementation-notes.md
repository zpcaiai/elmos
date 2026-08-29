# Implementation Notes

- Skill ID: `extension-sdk-and-codegen`
- Pack: `00-foundation-contracts`
- Kernel: `K0 Cross-Kernel Contracts`
- Priority: `P1`
- Capability: 提供新增知识连接器、Skill、验证器、训练器和部署适配器的 SDK 与脚手架。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
