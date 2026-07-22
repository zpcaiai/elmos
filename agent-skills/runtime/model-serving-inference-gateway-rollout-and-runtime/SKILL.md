---
name: model-serving-inference-gateway-rollout-and-runtime
description: 管理预测模型和生成模型的在线推理、批处理、Autoscaling、GPU感知路由、Canary和Fallback。
---

# Inference Platform

## Serving类型

ONLINE_SYNC
ONLINE_STREAMING
ASYNC
BATCH
EDGE
EMBEDDING
RERANKING
GENERATION

## Runtime Contract

Model Artifact
Protocol
Input Signature
Output Signature
Resource
Concurrency
Batching
Timeout
Health
Warmup
Shutdown

## Provider

KSERVE
SAGEMAKER_COMPATIBLE
VERTEX_COMPATIBLE
AZURE_COMPATIBLE
CUSTOM_KUBERNETES
SERVERLESS
VM
EDGE

KServe的生成式推理Runtime支持使用vLLM等后端，并提供OpenAI兼容Endpoint，可作为自托管推理Provider。

## Inference Routing

考虑：

Model
Adapter
GPU
KV Cache
Queue
Prompt Length
Priority
Tenant
Region
Residency
SLO

## Metrics

TTFT
Time per Output Token
End-to-end Latency
Throughput
Queue
Batch Size
GPU Utilization
Memory
Error
Cancellation

## Autoscaling

指标候选：

Request Queue
Active Sequence
Token Rate
GPU Memory
Latency
Concurrency

仅CPU利用率通常不足以描述LLM负载。

## Rollout

SHADOW
CHAMPION_CHALLENGER
CANARY
A_B
REGION
TENANT
FULL

## Fallback

Same Model Other Replica
Smaller Model
External Provider
Cached Answer
Rule-based Response
Human Escalation
Fail Closed

## 验收标准

- Runtime与Model分开；
- Protocol稳定；
- LLM指标包含Token维度；
- Routing可解释；
- Autoscaling使用推理指标；
- Fallback行为经过评测；
- Deployment绑定Model Digest。
