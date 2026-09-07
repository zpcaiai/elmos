# Batch 32：Performance、Capacity、Scalability与Cost Assurance

## Goal

以生产Workload验证吞吐、尾延迟、资源、扩缩容、Backpressure和单位成本，形成容量安全边际。

## Inputs

- Production workload profiles；
- SLOs；
- Target deployment；
- Cost models；

## Outputs

- Load/stress/spike/soak reports；
- Capacity plan；
- Performance baselines；
- Cost Pareto；
- Performance certificate；

## Execution Flow

1. 校准Workload；
2. 执行Load/Stress/Spike/Soak；
3. Profile CPU/Memory/GC/Event loop/Pool/Locks；
4. 验证Autoscaling/Cold start/Backpressure；
5. 计算Cost per request/journey/tenant；
6. 设置回归阈值；

## Verification

- P95/P99和Throughput通过；
- 容量有安全边际；
- 无无界Queue；
- 性能优化不破坏正确性；

## Stop Conditions

- 测试负载不代表生产；
- 尾延迟超标；
- 成本通过关闭验证来降低；

## Gate

`Performance & Capacity Gate`

## Installable Skill

`agent-skills/runtime/b32-performance-capacity-cost/SKILL.md`
