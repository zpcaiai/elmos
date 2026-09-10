# 给 Codex / Claude Code 的主执行指令

你要在当前实际 Elmos 仓库中实现本包，而不是再生成一套方案文档。

1. 先读取仓库 AGENTS.md/CLAUDE.md、当前路由/四业务线入口、K8、数据库迁移、工作流、身份权限、Router、测试与CI。只做授权范围内的读；不执行未知 install/build hook。
2. 运行 `elmos-assurance-bootstrap`，交付 `repo-map.json`、复用/差距清单、老新 gate 映射草案、真实 native 工具链可用性。未看到源码，不得声称对应功能已经存在。
3. 冻结本次 source/target/contract/policy/environment/toolchain/test/data/comparator/rule RevisionSet 与风险范围。先批准 normative contract、oracle 与测试义务，再写实现。推导事实与批准事实分开。
4. 按 `roadmap/implementation-batches.yaml` 执行一个纵向切片。P0 覆盖所有安全契约，并选定一条真实 Golden Route；不要同时铺开整个语言/数据库笛卡尔积。
5. 每项代码改动必须包括对应自动测试、负例、集成点、数据库兼容、观测、撤销/回滚方案。生成测试不得读取候选实现来决定 expected value。
6. 每次提交前执行真实命令，保留退出码、工具精确版本、不可变输入摘要、原始报告摘要、失败和跳过。环境缺失明确 `NOT_RUN`，不得用 mock 或包级测试替代原生测试。
7. 冒烟成功后执行完整的已批准回归计划；增量测试只能加速反馈，不能冒充最终全回归。故障修复不得删测试、放宽容差、减分母、降低安全门槛或擅改规范。
8. Ethen 身份未配置、签署服务缺失、关键证明 UNKNOWN、原生运行缺失、证据不匹配，停止正式签发，返回可定位的 INCONCLUSIVE。
9. 输出当前批次改动文件、执行命令和结果、验收ID→证据映射、剩余阻塞、下一可执行批次。只有引用当前真实证据才可标记完成。

禁止：重建一套平行 Harness；增加未经批准的 canonical route；把 Elmos Router 交给网关；让 LLM 执行 PASS 的最终决策；让 repo/agent 提交根证书/自选信任策略；自动推送主分支或部署生产；伪造 customer acceptance。

## 推荐启动文本

“读取 .elmos/assurance-package-v4.0.0/CODEX_START_HERE.md，使用 elmos-assurance-orchestrator。
对当前仓库先执行 B00，再实现 B01–B03 的可运行纵向切片；复用现有架构。
不要停在设计文档；必须交付代码、可执行测试与真实证据。遇到外部工具或权限缺失，完成其它非阻塞工作，并保持相关验收 NOT_RUN/INCONCLUSIVE。
禁止签发真实证书、修改认证范围或放宽失败测试。后续按照批次依赖继续。”
