---
name: elmos-template-iot-timeseries
description: 生成 MQTT/OPC UA/传感器采集、事件流、时序存储、湖仓、告警和设备数字孪生数据路径。
version: 1.0.0
group: bigdata-templates
dependencies: ["elmos-bigdata-project-orchestrator"]
triggers: ["IoT/工业/传感器", "时序分析", "实时告警/设备监控"]
outputs: ["template-plan.json", "generated-project/"]
---

# IoT、工业与时序数据项目模板

## 目标

生成 MQTT/OPC UA/传感器采集、事件流、时序存储、湖仓、告警和设备数字孪生数据路径。

## 适用触发条件

- IoT/工业/传感器
- 时序分析
- 实时告警/设备监控

## 输入

- 设备测点协议
- 采样/边缘
- 告警规则
- 保留分析

## 执行流程

1. **TPLIOT-001** — 建立 device/twin/measurement/event/command 契约和设备身份。
2. **TPLIOT-002** — 生成边缘缓冲、断网续传、MQTT/Kafka、乱序和时钟漂移处理。
3. **TPLIOT-003** — 选择时序数据库、实时流处理和湖仓历史层组合。
4. **TPLIOT-004** — 设计 downsampling、retention、compression、hot/cold 和高基数标签。
5. **TPLIOT-005** — 生成规则/CEP 告警、状态机、维护和可视化。
6. **TPLIOT-006** — 验证断网、重复、漂移、乱序、突发、重连和历史补传。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `template-plan.json`
- `generated-project/`

## 验收标准

- 断网不丢已确认数据。
- 时钟/乱序策略明确。
- 高基数和保留成本受控。
- 告警有抑制/去重/恢复。

## 失败、降级与恢复

边缘资源不足时保留最小缓冲与降采样，并明确损失边界。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **TPLIOT-007** — 输入和授权范围已固化为不可变快照。
- [ ] **TPLIOT-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **TPLIOT-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **TPLIOT-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **TPLIOT-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **TPLIOT-012** — 未验证能力未被标记为生产完成。
