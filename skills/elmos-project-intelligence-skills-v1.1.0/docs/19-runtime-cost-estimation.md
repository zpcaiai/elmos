# 机器执行 ETA、Token 与成本模型

## 1. 输出契约

```yaml
estimate_id:
as_of:
project_revision_id:
pipeline:
system_wall_clock_eta:
  p50_seconds:
  p90_seconds:
  confidence:
stages:
  - name:
    p50_seconds:
    p90_seconds:
    queue_seconds:
resources:
  cpu_core_seconds:
  memory_gb_seconds:
  gpu_seconds:
  object_storage_gb:
tokens:
  input:
  output:
  cached:
costs:
  currency:
  model:
  compute:
  storage:
  total:
human_review_effort:
  p50_hours:
  p90_hours:
assumptions: []
risks: []
```

## 2. 特征

- LOC、文件数、平均/最大文件；
- 语言和框架；
- 构建单元、服务、数据库、Topic；
- 动态语言、反射、宏、代码生成、FFI；
- 目标图表、文档和 PPT 数量；
- Trace 数据量；
- 缓存命中；
- 模型、上下文、并发、配额；
- 队列和硬件；
- 预期测试范围；
- 历史相似任务。

## 3. 阶段模型

```text
queue
ingestion
fingerprint
parse
symbol resolution
graph build
architecture/flow/data
model retrieval/generation
diagram render
document/PPT assembly
build/test
export/sign
```

阶段可并行时使用关键路径而非简单相加。

## 4. 动态重估

- 每个 stage 开始/完成记录实际时长；
- 重新计算剩余 P50/P90；
- 缓存命中和重试即时影响 ETA；
- 模型限流和 worker 缩容进入预测；
- 展示“最主要三项不确定性”。

## 5. 费率

- Provider/Model/SKU；
- input/output/cached token；
- batch/flex 等处理模式；
- 生效日期、地区、币种；
- 汇率版本；
- 本地模型硬件折旧/电力/租赁；
- 费率过期时禁止输出无日期成本。

## 6. 强制展示规则

- 机器自主运行时间单列；
- 人工审核时间单列；
- 不得使用“需要 20 人日”回答系统多久生成；
- 不得只给单点时间；
- 低数据量时明确低置信度；
- 历史任务完成后做校准回溯。
