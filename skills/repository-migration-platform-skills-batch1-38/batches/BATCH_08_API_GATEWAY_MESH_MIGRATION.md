# Batch 08：API、RPC、Serialization、Schema、Gateway与Service Mesh Migration

## Goal

迁移通信契约和流量治理，保证身份、Deadline、Cancellation、Retry、Streaming与Mixed-Version兼容。

## Inputs

- API/RPC schemas；
- Gateway/Mesh configs；
- Client inventory；
- Protocol traces；

## Outputs

- Target contracts/SDKs；
- Gateway routes；
- Mesh policies；
- Compatibility matrices；
- CI evidence；

## Execution Flow

1. 恢复Logical Operations；
2. 生成REST/gRPC/GraphQL/WebSocket/SSE契约；
3. 迁移Serializer和Error model；
4. 协调Gateway与Mesh职责；
5. 运行旧新Client/Server矩阵；

## Verification

- 对象授权不丢失；
- 非幂等操作无危险Retry；
- Deadline单调传播；
- 旧新版本兼容；

## Stop Conditions

- 隐藏Endpoint或Client未知；
- 身份Header可伪造；
- 协议转换丢失流式语义；

## Gate

`CI1–CI5`

## Installable Skill

`agent-skills/runtime/b08-api-gateway-mesh-migration/SKILL.md`
