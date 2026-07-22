---
name: edge-ai-model-deployment-inference-drift-and-lifecycle
description: 管理Edge AI模型、硬件兼容、量化、推理、Shadow、漂移、回滚和云边模型生命周期。
---

# Edge AI

## Use Case

ANOMALY_DETECTION
PREDICTIVE_MAINTENANCE
VISION_INSPECTION
QUALITY_PREDICTION
ENERGY_OPTIMIZATION
ROBOT_PERCEPTION
SAFETY_ADVISORY
PROCESS_OPTIMIZATION

## Deployment Bundle

Model
Runtime
Preprocessor
Postprocessor
Calibration
Threshold
Hardware Profile
Input Contract
Output Contract
Fallback

## Hardware

CPU
GPU
NPU
FPGA
MCU
VENDOR_ACCELERATOR

## Compatibility

Architecture
Instruction Set
Driver
Runtime
Memory
Thermal
Power
Model Format
Precision

## 模型优化

QUANTIZATION
PRUNING
DISTILLATION
COMPILATION
OPERATOR_FUSION
HARDWARE_DELEGATE

优化后必须重新执行：

- Accuracy；
- Slice；
- Latency；
- Thermal；
- Power；
- Memory；
- Stability。

## 模式

OFFLINE_TEST
SHADOW
ADVISORY
HUMAN_APPROVED
LIMITED_AUTOMATION
CLOSED_LOOP_APPROVED

## Safety Boundary

AI输出不能直接覆盖：

- Safety Interlock；
- E-stop；
- Hard Limit；
- Protection Relay；
- Certified Control Logic。

## Drift

Sensor Drift
Input Drift
Process Drift
Product Drift
Environmental Drift
Model Drift
Calibration Drift
Camera Drift

## Offline

边缘模型必须：

- 本地可加载；
- 无云也能运行；
- 有版本；
- 有Fallback；
- 有Watchdog；
- 有资源限制。

## 验收标准

- 模型绑定硬件Profile；
- 优化后重新评测；
- 先Shadow再Advisory；
- Safety边界不可越过；
- Drift按现场Slice；
- 云断网保持安全行为；
- 模型通过OTA Ring发布。
