# Implementation Notes

- Skill ID: `cross-language-semantic-ir-compiler`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 把源语言解析为统一语义并按目标语言约束重新生成。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
