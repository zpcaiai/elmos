# ADR-0053: Outbound site Runner for edge and industrial modernization

## Status

Accepted on 2026-07-22.

## Decision

Implement Batch 24 behind an outbound-only site Runner. Central control never directly operates a PLC. Passive discovery and read paths precede bounded write paths; local safety policy overrides central orchestration. OTA, commands and site cutover each require dedicated authorization and recovery evidence. Store projections in `edge_industrial`.

## Consequences

Safety PLC modification, interlock bypass, alarm clearing, arbitrary write ranges and cloud-dependent safety loops are prohibited. Repository tests prove enforcement code, not site safety or HIL success.
