# Implementation Notes

- Skill ID: `cross-language-build-ffi-native-integration`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P1`
- Capability: 迁移依赖、构建、C ABI、Native 库、平台能力和发布。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
