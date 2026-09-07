# Elmos Functional Assurance & Certification Engine

Production-grade runtime engine for **Elmos Functional Assurance & Certification Skills v4.1.0**.

## Overview
- **Role:** Independent functional evaluation, TEVV, ISO/IEC 17025/17065 conformity decisioning, regulated sector profiling, WORM Merkle evidence sealing, and certificate lifecycle management.
- **Skills Bound:** 178 skills across 12 primary domain handler suites.
- **Adapters:** 112 formal standard and metrology adapters.
- **Security & Integrity:** Fail-closed authorization boundaries, tenant isolation, HSM-backed certificate signing, and tamper-evident Merkle logs.

## CLI Usage
```bash
elmos-functional-assurance evaluate --skill elmos-ai-e0-e5-certifier --input payload.json
elmos-functional-assurance certify --candidate-digest <sha256> --profile aviation-do178c
elmos-functional-assurance verify-certificate --cert-file cert.json
```
