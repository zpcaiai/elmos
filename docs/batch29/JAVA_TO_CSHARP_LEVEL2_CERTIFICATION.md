# Level 2 Route Certification Guide: `routes/java-to-csharp`

This document defines the mathematical, architectural, and verification framework for **Level 2 Route Certification** in Elmos Batch 29, using the benchmark route [`routes/java-to-csharp`](file:///Users/stephen/DevProjects/AIProjects/elmos/routes/java-to-csharp) as the canonical implementation.

---

## 1. Dual-Track Architecture Overview

In Elmos Batch 29, language modernization routes operate under a strict dual-layer assurance model:

```
+-----------------------------------------------------------------------------------+
|                                 Elmos Batch 29 Gate                               |
|                         (scripts/batch29/run_route_gate.py)                       |
+-----------------------------------------------------------------------------------+
                                         |
         +-------------------------------+-------------------------------+
         |                                                               |
         v                                                               v
+------------------------------------+          +------------------------------------+
|  Track A: Formal Equivalence       |          |  Track B: Operational Evidence     |
|  (Format 2: SMT2 & AST Proofs)     |          |  (Format 1: Independent Verified)  |
+------------------------------------+          +------------------------------------+
| * Binds AST & SMT2 theories        |          | * Binds local dev/holdout/rep runs |
| * Explicit compiler assumptions    |          | * Absorbs external receipts:       |
| * Status: `limited`                |          |   - independent_verification: PASS |
| * Decision: `NOT_CERTIFIED`        |          |   - external_execution: PASSED     |
| * Invariant: Undischarged proof    |          | * Status: `certified`              |
|   assumptions MUST FAIL CLOSED.    |          | * Decision: `CERTIFIED`            |
+------------------------------------+          +------------------------------------+
```

### Why Level 1 (Formal Track) is `limited / NOT_CERTIFIED`
Under Evidence Format 2 (`formal-equivalence.json`), the route formally proves equivalence between canonical normalized Java PSP and re-lifted C# PSP using SMT solvers (Z3 / CVC5). However, real-world compiler runtimes (Roslyn, OpenJDK) and memory semantics cannot be proven 100% sound mathematically in an airgapped test environment. 
Therefore, the formal proof carries explicit assumptions:
```json
{
  "status": "PROVED_UNDER_ASSUMPTIONS",
  "proof_strength": "THEOREM_UNDER_ASSUMPTIONS",
  "certification_status": "NOT_CERTIFIED"
}
```
The Batch 29 Quality Gate (`Gate R29-G`) strictly enforces:
> *"assumption-bound proof cannot certify a route"*

Any attempt to set `status: certified` under Format 2 with undischarged assumptions will fail-closed.

---

## 2. How to Reach Level 2 (`status=certified, decision=CERTIFIED`)

Level 2 certification is the **Operational Production Track** (Evidence Format 1). It is reached when external independent verification and execution evidence are formally absorbed into the route's certification manifest.

### Prerequisites for Level 2 Certification
1. **Three Complete Corpora Evidence**:
   - `local-development-evidence.json` (syntax and unit tests)
   - `local-holdout-evidence.json` (unseen metamorphic cases)
   - `local-representative-evidence.json` (real-world vertical slices)
2. **Absorbed External Receipts**:
   - `independent_verification`: `"PASSED"`
   - `external_execution`: `"PASSED"`
3. **Certified Capabilities**:
   - Critical capabilities in `route.json` promoted from `experimental` or `limited` to `certified` (with zero missing coverage).
4. **Digest-Bound Integrity**:
   - Exact SHA-256 and byte counts for all evidence artifacts bound into `certification.json`.

---

## 3. How to Test Level 2 Locally

We provide an automated rehearsal harness: [`scripts/batch29/rehearse_java_to_csharp_certification.py`](file:///Users/stephen/DevProjects/AIProjects/elmos/scripts/batch29/rehearse_java_to_csharp_certification.py).

### Command 1: Test Default Level 1 State
Verify that the default state is fail-closed, limited, and rejected from unauthorized certification:
```bash
python3 scripts/batch29/rehearse_java_to_csharp_certification.py --reset
```
**Expected Output**:
```
OK: .../routes/java-to-csharp
GATE PASS: java-to-csharp status=limited decision=NOT_CERTIFIED
```

### Command 2: Elevate and Verify Level 2 Certified State
Simulate external independent verification absorption and execute the official Batch 29 quality gate:
```bash
python3 scripts/batch29/rehearse_java_to_csharp_certification.py --certify
```
**Expected Output**:
```
Elevated route to Level 2 (certified, CERTIFIED).
OK: .../routes/java-to-csharp
GATE PASS: java-to-csharp status=certified decision=CERTIFIED
```

### Command 3: Run the 6 Anti-Tamper Negative Scenarios
Demonstrate that the gate rejects all malicious attempts to forge Level 2 certification:
```bash
python3 scripts/batch29/rehearse_java_to_csharp_certification.py --test-tamper
```

The 6 verified anti-tamper scenarios:
| # | Tamper Vector | Gate Enforcement Behavior |
|---|---------------|---------------------------|
| 1 | Missing `independent_verification` | `certified route requires independent verification PASSED` |
| 2 | Missing `external_execution` | `certified route requires external execution PASSED` |
| 3 | Status `certified` with decision `NOT_CERTIFIED` | `certified route requires certification_decision CERTIFIED` |
| 4 | No capabilities marked `certified` in support matrix | `certified route has no certified capabilities` |
| 5 | Undischarged proof assumptions in certified route | `assumption-bound proof cannot certify a route` |
| 6 | Corrupted SHA-256 or missing evidence run | `evidence run is missing` or `digest mismatch` |

---

## 4. Production Cutover Workflow

When transitioning from local engineering validation to real customer production:
1. **Never fabricate external tokens in git commits**.
2. When the customer's hardware or independent auditor completes verification, they emit an external signed attestation token.
3. The pipeline runs `rehearse_java_to_csharp_certification.py --certify` with the customer's auditor key and execution receipts.
4. The Batch 29 gate (`scripts/batch29/run_route_gate.py`) evaluates the cryptographic Merkle chain and promotes the route to `CERTIFIED`.
