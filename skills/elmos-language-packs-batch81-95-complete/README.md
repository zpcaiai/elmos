# ELMOS Language Packs — Batch 81–95 Complete

This package adds fifteen enterprise, industrial, scientific, platform, and specialized language ecosystems to ELMOS.

## Delivery groups

1. **Batch 81–85:** COBOL/Mainframe, SAP ABAP, database procedural languages, IEC 61131-3 PLC, MATLAB/Simulink.
2. **Batch 86–90:** Modelica/FMI, VB/Office, IBM i RPG, R, SAS.
3. **Batch 91–95:** Salesforce, Objective-C, Delphi, BEAM, Lua/OpenResty.

## Scale

- 15 batches
- 12 Skills per batch
- 180 Skills total
- Skill IDs PG223–PG402
- 15 schemas and 15 examples
- Individual batch ZIPs, three group ZIPs, full ZIP and TAR.GZ

## Design principles

- Each ecosystem has native semantic discovery, generation/modernization, validation, deployment, and certification—not merely text templates.
- Language-specific operational semantics, data types, transactions, runtimes, vendor tools, and safety boundaries are first-class.
- Every transformation preserves requirements, architecture, source provenance, artifact ownership, tests, and evidence.
- Physical, safety-critical, financial, clinical, and production-platform changes require independent approval and execution evidence.

## Install

```bash
unzip elmos-language-packs-batch81-95-complete.zip
cd elmos-language-packs-batch81-95-complete
./install.sh ~/.codex/skills
./validate.sh
```
