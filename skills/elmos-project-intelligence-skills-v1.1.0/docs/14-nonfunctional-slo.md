# 非功能需求、性能预算与 SLO

## 1. 仓库规模档位

| 档位 | LOC | 文件 | 服务/模块 | 目标策略 |
|---|---:|---:|---:|---|
| S | ≤100k | ≤5k | ≤20 | 单 worker/快速全量 |
| M | 100k–500k | ≤25k | ≤100 | 分片并行 |
| L | 500k–2M | ≤100k | ≤500 | 分布式、优先索引 |
| XL | >2M | >100k | 多仓库 | System Workspace、分层/按需 |

性能数值是目标基线，必须通过真实环境压测校准，不能作为无条件承诺。

## 2. 交互 SLO

| 操作 | 目标 |
|---|---|
| 项目/文件树首屏 | p95 ≤ 2s（已导入） |
| 打开普通代码文件 | p95 ≤ 500ms 元数据，内容流式 |
| Definition/References 首批 | p95 ≤ 1s |
| 图谱邻居查询 | p95 ≤ 800ms |
| 混合搜索 | p95 ≤ 2s |
| 已缓存讲解/图表 | p95 ≤ 1s 元数据返回 |
| Job 状态更新 | ≤ 2s 可见 |
| 权限撤销 | 缓存/分享 ≤ 60s 失效 |

## 3. 批处理目标

| 任务 | S | M | L |
|---|---:|---:|---:|
| Manifest+Fingerprint | ≤1m | ≤3m | ≤10m |
| 初始静态索引 | ≤5m | ≤20m | ≤90m |
| 1% 文件增量 | ≤10% 初始耗时 | ≤10% | ≤10% |
| 常规架构图 | ≤30s | ≤60s | ≤120s/分层 |
| 常规文档章节 | ≤60s | ≤120s | 分批 |
| 20 页 PPT | ≤5m | ≤10m | ≤20m |

以上为产品目标；实际 UI 必须显示遥测校准的机器 wall-clock P50/P90，而非固定倒计时。

## 4. 可靠性

- 控制面月可用性目标 99.9%；
- 已确认 Artifact 读取目标 99.95%；
- worker 丢失后恢复成功率 ≥99%；
- 重复外部副作用目标 0；
- 检查点 RPO：最近完成分析单元；
- Control Plane 数据 RPO/RTO 按部署档位；
- 缓存/图/搜索故障可降级，不损坏事实源。

## 5. 质量 SLO

- Confirmed claim 无证据比例 = 0；
- 关键 claim 引用有效率 ≥99.5%；
- 人工锁定保留率 = 100%；
- 跨租户泄漏事件 = 0；
- 解析失败有诊断覆盖率 = 100%；
- 模型/规则升级必须通过黄金评测；
- stale artifact 不得标 Approved/Certified。

## 6. 资源与配额

- 每项目文件数、单文件、压缩包、对象存储、图节点、并发 Job；
- 模型 Token、渲染 CPU、导出大小；
- 软告警、硬限制和管理员 override；
- 公平调度避免单租户占满；
- XL 项目可选择分模块、只读或低优先级任务。

## Debug SLO

- 已缓存 Runtime Profile 的 workspace ready p95；
- launch-to-first-breakpoint p95；
- continue/step/pause 命令 p95（分离目标进程自身耗时）；
- variables 首屏和分页 p95；
- WebSocket 重连恢复 p95；
- 权限撤销生效 p95；
- terminate-to-cleanup-attestation p95；
- adapter crash isolation、replay success、redaction leak 与 Source/Target divergence 指标；
- 所有指标按 runtime、adapter version、tenant tier 和环境分层。
