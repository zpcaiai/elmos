# ELMOS Composite Engine fixtures

Batch 13 is a system-level control layer above the Java, .NET and Python engines. This directory contains portable fixtures and policy declarations only. The executable, framework-free control domain is in `modules/composite-modernization`; there is deliberately no fourth `/engine/v1` source transformation worker here.

The control plane can evaluate traffic and decommission decisions, but provider mutations, production write ownership, irreversible actions and decommission remain external, evidence-bound, human-approved operations.
