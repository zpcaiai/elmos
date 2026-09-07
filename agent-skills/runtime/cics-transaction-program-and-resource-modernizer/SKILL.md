---
name: cics-transaction-program-and-resource-modernizer
description: Inventory and modernize CICS regions, transaction IDs, programs, links, COMMAREAs, channels, containers, BMS maps, pseudoconversations, security contexts, files, Db2, MQ, and web-service assets. Use for CICS API enablement, channel migration, service extraction, or transaction cutover.
---

# CICS Modernization

## Model the transaction

1. Keep region, transaction ID, initial program, linked programs, resources, and external calls distinct.
2. Model `COMMAREA_CONTRACT`, `CHANNEL_CONTRACT`, and `CONTAINER_CONTRACT` separately with length, layout version, direction, optionality, status, and error areas.
3. Capture RETURN TRANSID, COMMAREA or TSQ state, next transaction, screen state, timeout, and authorization for pseudoconversations.
4. Catalog existing SOAP, JSON, MQ, and z/OS Connect interfaces before proposing a new facade.
5. Select `KEEP_CICS`, API enablement, channel modernization, CICS Java, extraction, rewrite, or retirement per capability.

## Preserve behavior

- Version or adapt a changed COMMAREA length; never silently widen the binary contract.
- Include every required channel container, including control and error containers.
- Propagate external identity into a constrained SAF/CICS authorization context; forbid a shared high-privilege identity.
- Keep original transaction boundaries and make extracted services independently reversible.
