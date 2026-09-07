# 增量集成与兼容边界

本包1.0.0不改Elmos全局版本、K1–K8、16个路由或独立认证体系。ao.v1只定义优化边界，宿主已有同义契约应映射而非覆盖。
保留既有Live Workbench的SourceAnchor、真实DAP、600秒预览与配额。现有设计不证明主仓库实现；B0必须读实际代码。

| 本次能力 | 旧设计候选owner | 应做的事情 |
|---|---|---|
| 源码精确导航 | elmos-online-code-reader / elmos-semantic-navigation | 复用原文件/符号接口 |
| 解释与上下文 | elmos-code-explanation / elmos-rag-query-planner-optimizer | 扩展薄接口与真实消费者 |
| 引用/污染控制 | elmos-rag-citation-provenance-chain-verifier / elmos-rag-memory-poisoning-verifier | 复用证据与安全检查，不复制认证 |
| 图谱/索引 | Semantic IR / Project Intelligence Graph | 增量投影，保留typed关系 |
| 教学 | elmos-debug-learning-copilot | 可替换子流程，不改DAP核心 |
| 执行/编排 | 当前Harness/ModelGateway/ExecutionGateway/durable runtime | 不另造状态、重试、预算或权限权威 |
| 认证 | 现有K8/独立认证包 | 只提交证据，不自签完成 |

每个逻辑端口映射owner、path、symbol、revision、existing/partial/missing/conflict/unknown、证据、真实测试命令和reuse/extend/adapt/create/block。
没有源码证据留null/unknown，不编造apps/api等目录。完整已有能力先补基准/回归，避免重复服务。
安装器只新增`.agents/skills/elmos-ai-optimization`。不合并/覆盖旧Skill、不编辑AGENTS、不改生产代码/数据库/依赖锁。
需要合并旧Skill时在授权工作树显式审查diff；当前安装器不做覆盖升级。
同包卸载仅删安装hash仍一致的文件，保留修改和新增文件；对可信本地工作树使用，不宣称对抗恶意并发文件系统。
模型/后端真实测试复用宿主凭据流，不暴露密钥。本包无模型API调用，不需要API密钥。
