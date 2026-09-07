---
name: ims-tm-db-message-and-hierarchical-data-modernizer
description: Discover and modernize IMS TM transactions, messages, programs, queues, OTMA, IMS Connect, MFS, plus IMS DB DBD, PSB, PCB, segments, keys, positions, indexes, checkpoints, and recovery. Use for IMS API facades, transaction extraction, hierarchical-data migration, or IMS retirement.
---

# IMS TM and DB Modernization

## Separate interaction and data

1. Model IMS TM transaction codes, input/output messages, programs, queues, OTMA, IMS Connect, MFS, security, and schedules independently from IMS DB.
2. Model DBD, PSB, PCB, segment parent/child order, keys, search fields, indexes, logical relationships, and access paths.
3. Preserve GU/GN/GNP and hold-call current-position behavior, ISRT/REPL/DLET effects, CHKP/XRST, and recovery boundaries.
4. Treat IMS Connect as an optional controlled facade, not evidence that transaction or data semantics are portable.
5. Map MFS input/output descriptors, fields, PF keys, transactions, and errors to explicit contracts.

## Gate migration

- Do not flatten repeated segments without occurrence order and parent/child identity.
- Reproduce navigation semantics before replacing DL/I calls with relational queries.
- Require behavior evidence for hierarchical transforms, checkpoint, restart, and message ordering.
