# ADR-0045: Independent mainframe and core legacy modernization engine

## Status

Accepted for Batch 19 repository scope on 2026-07-21.

## Context

Mainframe modernization is not equivalent to COBOL-to-Java translation. Business behavior spans source and copybook versions, compiler and binder options, load modules, dynamic calls, CICS/IMS transactions, JCL and scheduler control, Db2/VSAM/file state, encoding, terminal journeys, security identity, runtime usage, restart, side effects, batch windows, and data authority.

ELMOS already provides shared tenant, workflow, approval, evidence, risk, test-quality, security, delivery, billing, and composite authorities. A mainframe execution domain must reuse them while keeping z/OS operations outside the control plane.

## Decision

Add `ELMOS_MAINFRAME` as a ninth independent Java 21 execution domain. Support keep/optimize, API enablement, mainframe modularization, hybrid extraction, governed language transformation, runtime/data replatforming, package replacement, and retirement per capability. Never treat migration off IBM Z as an intrinsic success metric.

Run z/OS discovery, build, test, parallel comparison, promotion, cutover, and decommission only through approved adapters. Bind every operation to a short-lived organization/environment/system/identity/job/dataset/program/resource lease. Keep discovery read-only and deny arbitrary JCL, control-plane execution, production dataset/loadlib/subsystem changes, shared privileged identity, writer switches, and retirement unless specifically authorized and independently approved.

Build an immutable estate twin and correlate source, compile inputs, load modules, runtime programs, transactions, jobs, data, and observed use. Preserve original and expanded copybook lineage, JCL control and data DAGs, CICS COMMAREA/channel/container distinctions, IMS position and hierarchy, Db2 bind behavior, VSAM indexes, file/GDG/encoding semantics, side effects, and external consumers.

Treat AI/vendor explanations, rules, tests, refactors, and transformations as candidates. Only business-owner approval makes a rule authoritative. Only same-input/same-data semantic and side-effect evidence can support equivalence. Online, batch, data-authority, stability, rollback, access revocation, and decommission remain independent non-compensating gates.

## Consequences

Repository tests can prove contracts, deterministic policy, tenant/idempotency boundaries, adapter and lease denial, rule authority, independent cutover governance, schemas, fixtures, and persistence structure. They cannot prove z/OS access, customer COBOL correctness, compiler/build success, CICS/IMS/Db2/VSAM behavior, production capacity, live parallel runs, traffic or writer cutover, RACF changes, or retirement. Those remain `NOT_CONFIGURED`, `NOT_RUN`, `INCONCLUSIVE`, or `BLOCKED` until authorized external evidence exists.
