# 风险、限制与待决策事项

## 1. 技术风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 动态语言/反射/代码生成 | 调用图不完整 | 候选边、运行 Trace、人工确认 |
| 大型多仓库图爆炸 | 查询与 UI 卡顿 | 分层、聚合、分页、预算 |
| 图表自动布局不稳定 | diff 噪声 | stable IDs、布局锁、语义 diff |
| 模型幻觉 | 错误文档/PPT | 事实表、Claim/Evidence 验证器 |
| 文档人工修改被覆盖 | 用户不信任 | 三方合并、锁定、版本 |
| Trace 采样有限 | 误判不存在 | 时间/环境/采样标签 |
| Parser 版本升级 | 图谱变化 | 版本化、重建、质量对比 |
| 多存储复杂 | 运维成本 | Port/Adapter、明确事实源、可重建投影 |
| Renderer 安全 | RCE/XSS/SSRF | 沙箱、禁网、消毒、限制 |
| ETA 误差 | 用户预期失真 | 历史校准、P50/P90、动态重估 |

## 2. 产品风险

- 功能太多导致 P0 无法形成闭环；
- 误做完整在线 IDE；
- 演示图好看但无证据；
- 文档/PPT 生成优先于项目理解底座；
- 低价套餐成本不可控；
- 企业源代码隐私不足；
- 转换结果“编译通过”被误卖为“迁移成功”。

## 3. 待项目决策

1. 图数据库默认采用 Neo4j、Memgraph 还是 PostgreSQL AGE？
2. Search 默认 OpenSearch，还是 P0 使用 PostgreSQL FTS + pgvector？
3. 企业 API 继续 Java/Spring，还是独立 Rust/Go Control Plane？
4. Temporal 是否已在 Elmos 基础设施中？
5. 文档/PPT 的首选生成链和企业模板存储方式？
6. P0 支持哪些语言达到“完整语义导航”，哪些仅基础解析？
7. Runtime Trace 首先接入 OTLP 文件、Collector 还是平台连接器？
8. 私有化是否必须支持完全无外部模型？
9. 图表在线编辑首期采用 Cytoscape/Vue Flow 还是独立 Canvas？
10. E1–E5 与 Elmos 现有认证体系如何合并？

这些决策不阻止先实施接口与 Adapter，但在相应批次结束前必须以 ADR 冻结。

## 在线调试风险

- 不同 adapter 能力不一致：以运行时 capability negotiation 和合规矩阵解决。
- 构建/启动慢：使用内容寻址依赖缓存和预热 Runtime Profile，但不复用租户可写层。
- 调试改变时序和并发：报告 Heisenbug 风险，并结合 Trace/Replay/多次运行。
- 分布式协同暂停引发死锁：仅限受控环境，使用短租约、自动恢复和服务虚拟化。
- Replay 不完全确定：记录随机、时钟、外部服务和容差，输出 determinism score。
- 学习 Copilot 过度提示：Challenge 模式分层 Hint 和 Reveal 门禁。
- 生产数据风险：默认合成/脱敏，生产 attach 默认拒绝。
