---
name: mainframe-api-event-and-compatibility-facade-builder
description: Design versioned APIs, events, commands, queries, batch requests, file contracts, and compatibility facades over CICS, IMS, Db2, MQ, COMMAREA, channel/container, copybook, and business-rule capabilities. Use for z/OS Connect, contract-first API enablement, error mapping, or native-layout compatibility.
---

# Mainframe Interface Modernization

## Build contract first

1. Select a business capability and canonical contract before mapping a native layout.
2. Map OpenAPI or event fields to COMMAREA, channel/container, IMS message, Db2 procedure, MQ message, or batch dataset with full version lineage.
3. Handle EBCDIC, packed and zoned decimal, binary, filler, dates, REDEFINES, OCCURS, level-88 conditions, status areas, and native errors explicitly.
4. Map external identity through gateway identity to a constrained SAF, CICS, IMS, or Db2 authorization context.
5. Normalize COBOL return codes, CICS RESP/RESP2, IMS status, SQLCODE, abends, and business errors into stable external semantics.

## Govern compatibility

- Never expose an entire copybook as the public API by default.
- Version old-copybook/new-API translations, event upcasts/downcasts, and error mappings.
- Preserve the original transaction boundary and provide a tested rollback and facade-retirement plan.
