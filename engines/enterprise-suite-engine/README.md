# ELMOS Enterprise Suite Engine

Batch 21 的独立 Java 21 Worker，负责 SAP、Oracle、Dynamics 与 Salesforce 企业套件 Estate、配置与扩展、业务过程、主数据、角色/SOD、报表、数据迁移和并行切换候选。

默认端口为 `8095`。所有外部适配器初始均为 `NOT_CONFIGURED`；发现默认只读，Sandbox 验证、数据迁移、生产变更和主数据权威切换必须使用短期 Lease、精确 Environment Scope 与控制面独立批准。Worker 无权接受业务、财务、库存或 SOD 差异，也无权改变 Cutover 或 Decommission 结论。
