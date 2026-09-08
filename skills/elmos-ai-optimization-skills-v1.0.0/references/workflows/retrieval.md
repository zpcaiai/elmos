# 内部流程：证据检索优化

输入：实际消费者路径、固定revision、现有索引/权限接口、基线查询；先读SPEC 1–6。

1. 沿一个真实消费者追踪到源码、检索、权限和模型网关，记录快照如何传递。
2. 先写越权、旧版本、空命中和public DTO拒绝注入的contract tests。
3. 实现EvidenceContext薄层；先复用exact/lexical，已定位请求禁止embedding/LLM/rerank。
4. 每路召回都带可信tuple scope；候选正文发送前验证ACL、代次和CAS摘要。
5. 按需typed graph扩展，不穿越隐藏节点，不把候选边写成运行事实。
6. 接模型tokenizer进行预算打包，截断与anchor同步；参考bytes计数不可直接用于生产tokens。
7. 实现完整缓存key、命中鉴权、tombstone及generation发布。先正确再提速。
8. B2经批准再对照hybrid/rerank，ANN underfill不扩大授权；vector故障安全回退lexical。
9. 接一个真实入口、影子读和flag回滚；不要只交接口或Mock页面。
10. 运行宿主E2E、安全/撤权/删除/并发/版本与性能评测，记录实际命令和原始证据。

停止：身份/版本无法验证、隐私失败、索引空间不匹配。可降级为有证据的静态解释，但不可放松鉴权。
交付：实际diff、契约映射、测试/基准、index/cache策略、rollback和未执行清单。
