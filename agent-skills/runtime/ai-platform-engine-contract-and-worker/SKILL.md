---
name: ai-platform-engine-contract-and-worker
description: 实现AI／ML与生成式AI平台引擎、CPU/GPU Runner、Provider Adapter和ELMOS统一契约。
---

# AI Platform Engine

## Capability

{
  "engine": "ELMOS_AI_PLATFORM",
  "engineVersion": "1.0.0",
  "capabilities": [
    "AI_ESTATE",
    "DATASET_GOVERNANCE",
    "FEATURE_STORE",
    "EXPERIMENT_TRACKING",
    "TRAINING_PIPELINE",
    "MODEL_REGISTRY",
    "MODEL_SERVING",
    "LLM_GATEWAY",
    "RAG",
    "AGENT_RUNTIME",
    "AI_EVALUATION",
    "GUARDRAIL",
    "RESPONSIBLE_AI",
    "AI_FINOPS"
  ]
}

## API

GET  /engine/v1/capabilities
POST /engine/v1/discover
POST /engine/v1/plan
POST /engine/v1/train
POST /engine/v1/evaluate
POST /engine/v1/deploy
POST /engine/v1/monitor
GET  /engine/v1/jobs/{jobId}
POST /engine/v1/jobs/{jobId}/cancel

## Worker职责

- 读取AI Estate；
- 选择CPU、GPU、RAG或Agent Runner；
- 获取Dataset和Artifact Lease；
- 执行训练、索引或评测；
- 上传Model和Evidence；
- 记录GPU与Token；
- 清理环境。

## 默认禁止

- 使用未经批准生产数据；
- 下载不可信模型到控制平面；
- 自动发布生产模型；
- 自动授予Agent生产写权限；
- 自动接受Responsible AI风险；
- 将Prompt明文数据写入普通日志；
- 使用测试模型冒充生产模型。

## 验收标准

- AI Engine独立部署；
- CPU和GPU Runner分开；
- Provider可替换；
- Data和Artifact有Lease；
- 所有训练与推理可追踪；
- Agent不能自行批准上线。
