# 参考实现边界

Authority/Scope/Lease为内部测试对象，不是session鉴权、签名验证或完整生产ABAC；不得让客户端自行构造。
SQLite FTS5真实执行文本匹配，但为隔离候选每次构建授权小索引，不是生产性能推荐。
向量为手工合成输入，不运行Embedding、Reranker或LLM；不能宣传语义质量/模型成本改善。
索引与动作SQLite模型仅验证局部状态、CAS、稳定identity及对账规则，不实现真实CDC/外部执行器/跨进程exactly-once。
自制有界状态机不是LangGraph。原生可选示例资格单列；代码能导入/编译不证明持久恢复。
bytes不是tokens；source-data标签不是实际LLM注入红队；schema不证明语义、授权或引用支持。
本地release precheck不验签不批准生产；SHA只验证完整性。
安装器针对可信本地工作树，拒绝明显越界和symlink，不宣称对抗恶意并发文件系统。
本包未修改Elmos主仓库，未跑真实600秒、DAP、云端多租户、源目标DB或实际模型E2E。
参考代码迁入宿主前必须按真实存储/鉴权/并发契约重新实现和验收，不能改名就称生产化。
