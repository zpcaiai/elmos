# test-runner-adapter

**Providers:** JUnit/pytest/dotnet test/go test/cargo test

**Scope:** test discovery, execution, coverage and result normalization.

This directory is an implementation contract, not a live integration. Implement the abstract Elmos port, negotiate capabilities and versions, enforce environment-owned authority, return typed results, and pass every case in `conformance.yaml`. The Adapter never owns semantic truth, routing, or completion.
