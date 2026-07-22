---
name: ota-firmware-software-config-and-fleet-update-orchestrator
description: 管理设备固件、边缘软件、PLC配置和模型的签名、兼容、分环发布、恢复与Fleet治理。
---

# OTA Orchestration

## Artifact类型

FIRMWARE
BOOTLOADER
EDGE_APPLICATION
CONTAINER_IMAGE
DEVICE_CONFIGURATION
PLC_PROJECT_CANDIDATE
AI_MODEL
DRIVER
CERTIFICATE_BUNDLE

## Update Manifest

Artifact Digest
Target Model
Hardware Revision
Current Version Range
Dependencies
Conflicts
Release Counter
Signature
Minimum Battery / Power
Minimum Disk
Rollback Support
Health Check

## Release Ring

LAB
SPARE_DEVICE
INTERNAL_SITE
PILOT_DEVICE
PILOT_CELL
PILOT_LINE
SITE_PERCENTAGE
FLEET_PERCENTAGE
FULL

## Update状态

ELIGIBLE
DOWNLOADING
VERIFIED
STAGED
INSTALLING
REBOOTING
HEALTH_CHECKING
SUCCESS
ROLLED_BACK
FAILED
MANUAL_RECOVERY

## 安全验证

Signature
Hash
Target Device
Hardware Compatibility
Version
Expiry
Dependency
Release Counter

## 攻击防护

需要应对：

- Rollback；
- Freeze；
- Mix-and-match；
- Arbitrary Artifact；
- Replay；
- Partial Installation。

Uptane通过Root、Timestamp、Snapshot、Targets等签名元数据以及设备和硬件标识管理这些风险，可作为高保障OTA Adapter。

## Power Loss

测试：

- 下载中断；
- 写入中断；
- Boot中断；
- 首次启动失败；
- Health失败；
- A/B回退；
- Recovery Mode。

## PLC更新

PLC Program Update默认：

MANUAL_CONTROLLED
VENDOR_TOOL
ENGINEERING_APPROVAL
PRODUCTION_WINDOW
BACKUP
CHECKSUM
ROLLBACK

不能使用普通IoT OTA自动全量下发。

## 验收标准

- Artifact签名；
- 硬件兼容明确；
- 发布按Ring；
- Power Loss可恢复；
- 失败自动停止Campaign；
- PLC与普通设备策略分开；
- 每台设备返回实际安装证据。
