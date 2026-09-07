---
name: jcl-procedure-scheduler-and-batch-flow-analyzer
description: Parse JCL, PROC, symbolic parameters, DD statements, datasets, conditions, return-code policies, restart points, calendars, and enterprise scheduler dependencies into separate control and data DAGs. Use for batch discovery, critical-path analysis, restart planning, or scheduler migration.
---

# JCL and Batch Flow Analyzer

## Construct the batch model

1. Parse JOB, EXEC, DD, PROC/PEND, INCLUDE, SET, IF/THEN/ELSE, COND, OUTPUT, and JCLLIB.
2. Expand procedures and symbolic parameters using the version and library order actually used by the build or scheduler.
3. Model sequential, PDS/PDSE, VSAM, GDG, temporary, SYSOUT, in-stream, tape, and utility inputs with disposition and generation semantics.
4. Separate step-control edges from dataset producer/consumer, condition, scheduler, calendar, resource, and manual-approval edges.
5. Interpret step RC, maximum RC, custom business codes, abends, utility codes, and scheduler overrides; `Ended` alone is not success.
6. Record JCL restart, application checkpoint, utility restart, cleanup, and non-restartable boundaries.

## Gate migration

- Preserve conditional execution and relative GDG references.
- Compare EBCDIC sort and target collation, control totals, intermediate outputs, and final outputs.
- Block the batch plan when external scheduler dependencies, calendars, return-code semantics, or restart behavior remain unknown.
