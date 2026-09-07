---
name: progressive-site-line-cutover-rollback-and-decommission
description: 按设备、工位、Cell、产线和工厂渐进切换边缘、SCADA、协议、Twin、AI和控制能力。
---

# Industrial Cutover

## Cutover单元

DEVICE
ASSET
CELL
LINE
AREA
SITE
PROTOCOL
TAG_GROUP
SCADA_FUNCTION
EDGE_APPLICATION
AI_MODEL

## 阶段

DISCOVERY
PASSIVE_READ
MIRROR
DIGITAL_SHADOW
ADVISORY
HUMAN_APPROVED_WRITE
LIMITED_CONTROL
PRIMARY_CANDIDATE
PRIMARY
STABILITY_HOLD
LEGACY_STANDBY
LEGACY_READ_ONLY
DECOMMISSION

## Read Cutover

优先切换：

- 数据采集；
- Historian；
- Dashboard；
- 报表；
- Analytics；
- Twin。

## Write Cutover

后切换：

- Config；
- Setpoint；
- Command；
- Recipe；
- Sequence；
- Control。

## Command Authority

LEGACY_ONLY
LEGACY_PRIMARY_NEW_ADVISORY
HUMAN_SELECTS
NEW_LIMITED
NEW_PRIMARY_LEGACY_FALLBACK
NEW_ONLY

## Freeze

切换前冻结：

PLC Program
Tag Mapping
Gateway Config
Certificate
Edge Artifact
Model
Twin Contract
Network Policy

## Rollback

DATA_ROUTE
TELEMETRY_ROUTE
GATEWAY
EDGE_APP
AI_MODEL
SCADA_SCREEN
COMMAND_AUTHORITY
CONTROL_LOGIC
FULL_CELL

## Point of No Return

可能包括：

- 旧设备配置被覆盖；
- 旧PLC项目丢失；
- 新设备替换旧硬件；
- 新Recipe写入；
- 旧SCADA License取消；
- 历史格式不再可读；
- Safety重新认证。

## Decommission

确认：

- 无Telemetry；
- 无Command；
- 无Operator使用；
- 无Historian Consumer；
- 无Partner；
- 无备用用途；
- Certificate撤销；
- Network Rule删除；
- 配置归档；
- PLC Project归档；
- License处理；
- Spare和Recovery计划更新。

## 验收标准

- 读写切换分开；
- 以Device／Cell为最小灰度单元；
- Command Authority唯一；
- Freeze Manifest完整；
- Rollback经过现场演练；
- Stability Hold跨越完整生产周期；
- 退役依据运行证据。
