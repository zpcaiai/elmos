# 宿主API与数据映射

路径是逻辑建议，B0复用实际API；不声称这些服务/表已存在。
POST /evidence/context：public ContextRequest；原session鉴权；响应EvidenceContext与typed错误。
POST /agent-subflows：host调度，返回checkpoint/status/ref，不提交Run完成。
POST /actions/propose：仅提交候选意图；批准/dispatch/reconcile走现有网关。
GET /evidence/{ref}：每次校验scope/撤权，不允许公共缓存。
POST /external-knowledge/retrieval：Dify专用service身份绑定knowledge/principal，保持终端用户权限边界。

数据对象映射：ContextRequest/Audit、ProjectionManifest、Outbox/CDC checkpoint、Evidence/Cache metadata、AgentSubflowCheckpoint、ActionIntent/Receipt、Benchmark/FeatureDecision。
复用PostgreSQL事务和原outbox/ledger；大正文CAS、cache非事实源。新表先expand/backfill验证，再切换，不自动运行假定DDL。
HTTP建议400 schema、401身份、403权限、409 stale、422 embedding mismatch、429 budget、503依赖；错误不泄漏私有资源。

Reference Request含query_vector/context_bytes用于离线实验，**不是public HTTP DTO**。生产由网关生成embedding，按实际tokenizer打包。
TypeScript使用camelCase逻辑接口，JSON使用snake_case边界；适配时显式转换并契约测试，不能直接强制类型断言跳过。
Reference Authority/Lease只是测试double，不是host签名/鉴权。Schema只证明形状，权限有效、字节真实性、引用支持、签名与CAS原子性由独立代码验证。
