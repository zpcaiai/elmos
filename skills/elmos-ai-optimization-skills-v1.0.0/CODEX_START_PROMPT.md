# 复制给Codex

请启用 `$elmos-ai-optimization`；未安装时读取我提供的包目录中的SKILL.md。
在当前已授权的Elmos工作树实施，先读适用AGENTS.md、INTEGRATION.md、SPEC.md、IMPLEMENTATION_PLAN.md。
先完成B0：查实际代码、调用者、测试和revision，映射已有owner；不要把设计文档或文件名当实现证明。
默认本轮B0+B1：复用索引/权限/模型网关，完成统一EvidenceContextService并接一个真实源码解释入口，随后做宿主E2E、权限/版本、缓存撤权和基准对照。
不要默认同时引入LangChain、LangGraph、Dify、ES和独立向量库；B2–B5按ADR和真实验收启用。
保持K1–K8、16路由、独立验收、Result Commit、3槽和600秒租约。不以图完成当产品完成。
环境缺失标blocked/not_run并继续安全独立任务；不索要明文Secret，不在宿主运行不可信仓库。
每批输出真实diff、命令/退出码/日志证据、质量/latency/cost、回滚和未完成项，不只交文档/空接口/Mock。
不自动部署、公网发布、创建付费资源、push或执行破坏性迁移；包内测试与实际Elmos测试分列。
