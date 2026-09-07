# Implementation Notes

- Skill ID: `credit-wallet-and-reservation`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P0`
- Capability: 在长任务开始前预留余额，按实际用量结算、释放和处理超额。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
