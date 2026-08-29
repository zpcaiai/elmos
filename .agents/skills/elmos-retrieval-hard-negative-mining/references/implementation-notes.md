# Implementation Notes

- Skill ID: `retrieval-hard-negative-mining`
- Pack: `03-retrieval-context-engineering`
- Kernel: `K3 Retrieval and Context Kernel`
- Priority: `P1`
- Capability: 从高相似但错误版本、错误框架和同名符号中构造困难负样本。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
