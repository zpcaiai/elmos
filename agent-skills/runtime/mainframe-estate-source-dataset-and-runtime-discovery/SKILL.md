---
name: mainframe-estate-source-dataset-and-runtime-discovery
description: Discover and reconcile mainframe applications, source members, copy libraries, compiler and binder inputs, load modules, JCL, datasets, subsystem resources, runtime usage, ownership, and seasonal activity. Use for estate inventory, source-to-runtime mapping, unknown-owner analysis, and retirement readiness.
---

# Mainframe Estate Discovery

## Build the estate twin

1. Inventory COBOL, PL/I, assembler, REXX, JCL, PROC, INCLUDE, copybook, BMS, MFS, SQL, and DDL from approved sources.
2. Capture compiler options, precompilers, copylib search order, binder maps, link libraries, load modules, and promotion metadata.
3. Inventory CICS and IMS transactions, batch jobs, Db2 plans, MQ, VSAM, datasets, and scheduler dependencies.
4. Correlate `source member -> compile unit -> load module -> runtime program -> transaction or job`; never infer identity from names alone.
5. Record evidence windows and classify use as `ACTIVE`, `SEASONAL`, `DORMANT`, `HISTORICAL`, or `UNKNOWN`.

## Gate conclusions

- Emit `RUNTIME_SOURCE_MISMATCH` when active code lacks authoritative source or build lineage.
- Preserve conflicting SCM, PDS/PDSE, package-manager, listing, and loadlib candidates.
- Treat a short observation window, unknown owner, or absent trace as risk, not proof of dead code.
- Produce immutable estate, source-runtime, load-module, dataset, runtime-usage, and unknowns artifacts.
