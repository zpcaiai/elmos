# Batch 97–104 Validation

Run `./validate.sh` from this directory. If the system Python does not provide `jsonschema`, the entrypoint uses `uv` with `jsonschema==4.25.1`; schema validation is never silently skipped.

The validator checks the exact 128-Skill and eight-Batch identity set, immutable file inventory and checksums, split-manifest parity, catalog/runtime parity, dependency DAG, generated Codex interfaces, strict JSON Schemas and templates, and compilation of every selected Markdown Skill into a non-empty executable contract. The test suite adds malformed-contract, graph-cycle, duplicate-node, dangling-edge, fabricated-evidence and unauthorized-global-ID regression cases.

`scripts/run_certification_gate.py` requires content digests, exact byte counts, evidence roles, authorization, attested runtime references, required P0 results and a distinct independent verifier. It rejects missing, path-escaping, changed or unbound evidence. Its maximum local decision is `ready_for_external_gate` with `certified: false` because external signature and trust-store verification are intentionally outside this package.

These checks are engineering evidence only. Real runner isolation, route equivalence, recovery, scale, security campaigns, customer acceptance, support readiness and Product Certification remain `NOT_RUN` until authorized execution produces independently verified evidence.
