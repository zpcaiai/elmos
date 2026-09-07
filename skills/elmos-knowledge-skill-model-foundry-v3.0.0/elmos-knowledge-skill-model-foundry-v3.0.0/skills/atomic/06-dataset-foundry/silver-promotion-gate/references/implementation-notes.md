# Implementation Notes

- Skill ID: `silver-promotion-gate`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 要求基础编译、测试、来源和权限检查通过后进入可限制使用的数据层。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
