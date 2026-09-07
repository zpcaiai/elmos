# ELMOS Enterprise Integration Engine

Batch 20 的独立 Java 21 Worker，负责企业集成资产、Route/Contract/Delivery IR、ESB/MQ/Kafka/RabbitMQ/API Gateway/B2B/Workflow 现代化候选，以及契约、投递与并行迁移验证。

默认端口为 `8094`。所有外部适配器初始均为 `NOT_CONFIGURED`；发现默认只读，Replay、生产配置变更和切换必须使用短期 Lease、精确 Scope 与控制面独立批准。Worker 无权改变 Cutover 或 Decommission 结论。
