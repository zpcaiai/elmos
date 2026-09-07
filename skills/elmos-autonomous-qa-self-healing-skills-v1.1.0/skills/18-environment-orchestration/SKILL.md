---
id: 18-environment-orchestration
name: Environment Orchestration
version: 1.1.0
category: execution
depends_on:
  - 04-risk-coverage-planning
---

# Environment Orchestration

## 目标

按测试 profile 创建可复现、短生命周期、资源隔离的运行环境和依赖服务。

## 何时调用

当工作流进入 `18-environment-orchestration` 对应阶段，或上游技能产物变化导致本阶段失效时调用。不得跳过依赖技能直接伪造输入。

## 输入契约

- ProjectSnapshot、部署清单和依赖拓扑
- 环境 profile、资源配额、网络策略和秘密引用
- 数据库/消息/浏览器/设备/性能 Worker 需求

## 输出契约

- EnvironmentLease、端点、镜像/配置哈希和健康状态
- 构建、启动、校准、销毁日志
- 环境失败诊断和资源回收结果

## 执行步骤

1. 解析环境模板并绑定不可变镜像/依赖版本。
2. 创建隔离 namespace、网络、存储、数据库和消息依赖。
3. 只注入最小测试凭据，阻断生产端点。
4. 执行 readiness、Schema、时钟和资源校准。
5. 向测试分片发放有期限租约和连接信息。
6. 结束后幂等销毁；Reaper 回收孤儿资源。

## 不可违反的控制

- 性能测试和普通功能测试不得共享易干扰资源。
- 环境健康检查必须包含业务就绪而非仅端口打开。
- 秘密不得写入日志、报告或测试代码。
- 环境构建失败不得被标为产品缺陷。

## 完成判定

- 环境可从 manifest 完整重建。
- Worker 崩溃后租约到期可安全回收。
- 不存在生产网络/凭据误用。
- 环境诊断能区分基础设施、配置和产品失败。

## 失败处理

- 输入缺失或 Schema 不合法：标记 `BLOCKED`，保留诊断，不得猜测为成功。
- 可恢复基础设施失败：保存检查点并按受限策略重试。
- 产品或策略失败：生成结构化缺陷/门禁结果，不得通过跳过或弱化规则绕过。
- 所有失败均写入证据清单和审计事件。
