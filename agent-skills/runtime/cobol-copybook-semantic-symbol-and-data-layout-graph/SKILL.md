---
name: cobol-copybook-semantic-symbol-and-data-layout-graph
description: Parse COBOL structure and build traceable program, section, paragraph, statement, data-item, copybook, call, file, SQL, CICS, IMS, and byte-layout graphs. Use for copybook expansion, REDEFINES, OCCURS DEPENDING ON, COMP-3, EBCDIC, dynamic calls, and test-codec generation.
---

# COBOL and Copybook Semantic Graph

## Resolve semantics

1. Preserve original source and expanded views with include dataset, member, version, replacement rule, conditional compilation, and expansion location.
2. Resolve same-name copybooks using the recorded build search order; retain all conflicts and mark unresolved inputs `AMBIGUOUS`, `MISSING`, or `CONDITIONAL`.
3. Model division, section, paragraph, statement, data item, and external resource separately.
4. Record level, PIC, USAGE, sign, OCCURS, DEPENDING ON, REDEFINES, value, level-88 conditions, alignment, offset, byte length, and CCSID.
5. Distinguish static, literal dynamic, variable dynamic, CICS LINK/XCTL, IMS, Db2, MQ, and file calls with confidence and evidence.

## Protect layout integrity

- Bound OCCURS before decoding; never read later fields after an invalid count.
- Use a discriminator for mutually exclusive REDEFINES layouts.
- Verify packed/zoned decimal sign, scale, precision, invalid digits, overflow, rounding, and negative zero.
- Surface EBCDIC conversion, endianness, pointer, alignment, and level-88 loss as explicit findings.
