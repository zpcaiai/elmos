# 首批 40 个可执行任务

这些任务与 22 个 Skills 的 frontmatter 和 `skill-manifest.yaml` 一一对应。任务 ID 全局唯一；完成状态必须由产物和门禁证据决定。

| ID | Skill | 任务 | 依赖 | 完成定义 |
|---|---|---|---|---|
| MAPP-001 | `frontend-to-miniapp-orchestrator` | 定义 conversion request、run、artifact、gate、approval、cost 数据契约 | — | 14 个 Schema 的根契约与最小请求可验证 |
| MAPP-002 | `frontend-to-miniapp-orchestrator` | 实现可恢复状态机、检查点、幂等键和阶段裁剪 | MAPP-001 | 任务中断后从最近 checkpoint 恢复且不重复副作用 |
| MAPP-003 | `miniapp-source-framework-detector` | 实现只读、安全的仓库清单与内容哈希扫描 | MAPP-001 | fixture 文件覆盖率 100%，不执行仓库脚本 |
| MAPP-004 | `miniapp-source-framework-detector` | 实现多框架证据、版本范围、置信度与冲突检测 | MAPP-003 | Vue/React/Flutter/混合 fixture 检测结论可解释 |
| MAPP-005 | `vue-to-miniapp-analyzer` | 实现 Vue SFC、template、script、style AST 分析 | MAPP-003, MAPP-004 | Vue 2/3 fixture 全部节点带源位置 |
| MAPP-006 | `vue-to-miniapp-analyzer` | 实现 Router、Vuex、Pinia、生命周期与副作用提取 | MAPP-005 | 路由和 store 图闭合，动态项有风险记录 |
| MAPP-007 | `react-to-miniapp-analyzer` | 实现 TSX/JSX、组件、Hooks 与类生命周期分析 | MAPP-003, MAPP-004 | Hook 依赖、cleanup 和组件图可验证 |
| MAPP-008 | `react-to-miniapp-analyzer` | 实现 React Router、Redux、Zustand、MobX 与 Context 提取 | MAPP-007 | 路由、状态和异步 action trace 完整 |
| MAPP-009 | `flutter-widget-semantic-reconstructor` | 建立 Dart analyzer CLI 与类型/常量/类模型导出 | MAPP-003, MAPP-004 | Flutter fixture 可稳定输出 source facts |
| MAPP-010 | `flutter-widget-semantic-reconstructor` | 重建 Widget Tree、Navigator、状态库、动画与 Platform Channel | MAPP-009 | 页面/导航/状态图闭合，插件 100% 有结论 |
| MAPP-011 | `miniapp-semantic-ir` | 实现 Semantic IR v1 Schema、类型和稳定 ID | MAPP-005 | Vue 最小闭环可生成确定性 IR |
| MAPP-012 | `miniapp-semantic-ir` | 实现 IR 校验、版本迁移、确定性序列化与 trace index | MAPP-011 | 重复序列化哈希一致，迁移 fixture 通过 |
| MAPP-013 | `miniapp-capability-registry` | 建立四平台 versioned profile 与能力注册表种子 | MAPP-012 | 常用能力包含支持、权限、运行时、风险和资料时间 |
| MAPP-014 | `miniapp-capability-registry` | 实现 capability resolver、A-E 分类和组合冲突检查 | MAPP-013 | 所有 IR capability 有结论，C/D/E 全部披露 |
| MAPP-015 | `miniapp-component-mapping-engine` | 实现组件映射 DSL、匹配优先级与解释输出 | MAPP-012, MAPP-014 | 基础组件和表单 fixture 100% 有映射 |
| MAPP-016 | `miniapp-component-mapping-engine` | 实现组合组件生成、props/events/slots 与无障碍契约 | MAPP-015 | 复杂组件无空 stub，行为测试生成 |
| MAPP-017 | `miniapp-state-event-lifecycle-converter` | 实现状态作用域、派生值与 app/page/component 生命周期下降 | MAPP-012, MAPP-015 | 生命周期顺序和状态引用闭合 |
| MAPP-018 | `miniapp-state-event-lifecycle-converter` | 实现事件传播、异步副作用、cleanup、竞态与幂等计划 | MAPP-017 | 事件顺序与副作用账本可供差分测试 |
| MAPP-019 | `miniapp-style-layout-converter` | 实现 CSS/Flutter layout AST、单位和目标布局下降 | MAPP-012, MAPP-015 | 核心页面无未解释布局丢失 |
| MAPP-020 | `miniapp-style-layout-converter` | 实现 design token、主题、响应式、安全区和动画策略 | MAPP-019 | 主题和设备矩阵 fixture 达到视觉阈值 |
| MAPP-021 | `miniapp-third-party-dependency-migrator` | 实现依赖实际调用面、传递关系和平台专属信号分析 | MAPP-003 | 所有直接依赖有 usage evidence |
| MAPP-022 | `miniapp-third-party-dependency-migrator` | 实现保留/替代/重写/后端迁移/阻断及许可证供应链报告 | MAPP-021, MAPP-014 | 依赖决策、风险、测试与回滚完整 |
| MAPP-023 | `wechat-miniapp-codegen` | 实现微信原生 generator、adapter、配置、测试和 trace | MAPP-016, MAPP-018, MAPP-020, MAPP-022 | golden project 官方构建和关键流程通过 |
| MAPP-024 | `alipay-miniapp-codegen` | 实现支付宝原生 generator、CLI 元数据、测试和 trace | MAPP-016, MAPP-018, MAPP-020, MAPP-022 | golden project 官方构建和关键流程通过 |
| MAPP-025 | `douyin-miniapp-codegen` | 实现抖音原生 generator、场景/OpenAPI contract 和 trace | MAPP-016, MAPP-018, MAPP-020, MAPP-022 | golden project 官方构建和场景流程通过 |
| MAPP-026 | `xiaohongshu-miniapp-codegen` | 实现小红书原生 generator、授权/交易 contract 和 trace | MAPP-016, MAPP-018, MAPP-020, MAPP-022 | golden project 构建或可验证阻断，授权流程完整 |
| MAPP-027 | `miniapp-commerce-social-adapter` | 定义身份、会话、订单、支付、退款、分享和内容领域 contract | MAPP-014 | 平台无关状态机和服务端/客户端边界通过契约测试 |
| MAPP-028 | `miniapp-commerce-social-adapter` | 实现四平台商业/社交 adapter、sandbox/mock 和回调安全 | MAPP-027, MAPP-023, MAPP-024, MAPP-025, MAPP-026 | 订单幂等、验签、重放与补偿测试通过 |
| MAPP-029 | `miniapp-privacy-permission-auditor` | 实现权限、个人数据、存储、网络和第三方 SDK 数据流模型 | MAPP-014, MAPP-022 | 敏感数据流 100% 可追踪 |
| MAPP-030 | `miniapp-privacy-permission-auditor` | 实现 secret、日志、权限用途和审核披露扫描 | MAPP-029, MAPP-023, MAPP-024, MAPP-025, MAPP-026 | 高危 secret=0，权限与声明一致 |
| MAPP-031 | `miniapp-differential-testing` | 实现源/目标场景驱动和行为 trace 捕获 | MAPP-023, MAPP-024, MAPP-025, MAPP-026 | 关键流程可在相同 mock 数据下重放 |
| MAPP-032 | `miniapp-differential-testing` | 实现归一化、语义比较、定位和 flaky 隔离 | MAPP-031 | 差异关联到 source/IR/rule/target，关键流 100% 通过 |
| MAPP-033 | `miniapp-visual-regression-testing` | 实现设备矩阵、稳定截图、结构框和像素差分 | MAPP-020, MAPP-023, MAPP-024, MAPP-025, MAPP-026 | golden 页面可重复生成相同基线 |
| MAPP-034 | `miniapp-visual-regression-testing` | 实现关键区域加权、mask 审计和视觉修复候选 | MAPP-033 | 默认相似度门禁与文本/溢出检查生效 |
| MAPP-035 | `miniapp-auto-repair-loop` | 实现 finding 聚类、上游定位和最小补丁生成 | MAPP-030, MAPP-032, MAPP-034 | 相同缺陷优先修正规则而非一次性生成文件 |
| MAPP-036 | `miniapp-auto-repair-loop` | 实现有界修复状态机、重复补丁检测、回滚和受影响门禁 | MAPP-035 | 最大三次、无无限循环、失败可升级 |
| MAPP-037 | `miniapp-ci-build-release` | 实现四平台工具链 profile、隔离构建和可重现产物 | MAPP-030, MAPP-036 | 工具版本、退出码、产物哈希和日志脱敏完整 |
| MAPP-038 | `miniapp-ci-build-release` | 实现 preview/upload/review/release 分级审批与回滚 | MAPP-037 | 无批准不能越级，回执与版本可追踪 |
| MAPP-039 | `miniapp-migration-evidence-reporter` | 实现 claim/evidence graph、artifact index 和完整性校验 | MAPP-030, MAPP-032, MAPP-034, MAPP-038 | 所有关键 claim 有当前证据且哈希一致 |
| MAPP-040 | `miniapp-migration-evidence-reporter` | 生成兼容、测试、风险、成本、运行时和发布就绪报告 | MAPP-039 | ready/not-ready 与门禁一致，不把计划写成结果 |

## 执行规则

- 不要按表格顺序盲目串行执行；orchestrator 应按依赖图并行无冲突任务。
- 每个任务开始前校验上游 artifact 哈希；完成后写入 artifact index。
- 一项任务可以产生多个代码提交，但一个提交不得混合无关任务。
- 任何任务状态为 `blocked` 时，必须记录阻断主体、缺少信息、可重试条件和恢复点。
- 任何“完成定义”均不得以代理自述替代测试。
- 变更 Schema、IR 或公共 contract 时，必须重新运行所有下游 contract tests。
- 平台工具链、权限或审核阻断不允许伪造通过；可完成生成和离线验证部分，并保持门禁为 blocked。

## 建议首个闭环

`MAPP-001 → 003 → 004 → 005 → 006 → 011 → 012 → 013 → 014 → 015 → 017 → 018 → 019 → 020 → 021 → 022 → 023 → 029 → 030 → 031 → 032 → 033 → 034 → 035 → 036 → 037 → 039 → 040`

该闭环使用 `examples/vue3-todo`，先完成 Vue 3 → 微信，再扩展 React、Flutter 和其他三个目标平台。
