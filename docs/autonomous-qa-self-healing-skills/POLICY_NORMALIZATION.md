# Source Policy Normalization Ledger

The immutable source tree is never edited. Two source YAML files contain
indentation defects that make intended nested sections parse as `null`. The
compiled repository contracts record the defects and apply the following
reviewed interpretation only inside repository-owned runtime code.

## `policies/execution-policy.yaml`

Source shape:

```yaml
test_artifact_execution:

manifest_only_execution: true
materialization_required_before_execution: true
verify_artifact_hash_before_shard_start: true
execute_temporary_unmanifested_code: false
record_artifact_refs_per_attempt: true
```

Compiled interpretation: the five controls belong under
`test_artifact_execution`. The runtime enforces manifest-only execution,
materialization and hash verification, rejects temporary unmanifested code, and
records artifact references for each attempt.

## `policies/auto-fix-policy.yaml`

Source shape:

```yaml
artifact_update_rules:

rematerialize_changed_tests: required
preserve_previous_artifact_version: required
update_project_output_manifest: required
update_test_artifact_set: required
rebuild_required_bundles: required
failed_patch_must_not_replace_published_output: true
```

Compiled interpretation: the six controls belong under
`artifact_update_rules`. Repository-owned repair validation applies them without
changing the source bytes.

These repairs are provenance-bearing normalization decisions, not evidence that
the source package was complete or production-ready. Any future archive digest
change invalidates the decisions until reviewed again.
