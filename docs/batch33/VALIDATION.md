# Batch 33 Validation Report

Validation date: 2026-07-21

## Scope

Validated the installable Batch 33 Codex Skill overlay containing Skills 1223–1242, schemas, templates, deterministic tools, tests, installer, and the merged Batch 20＋29＋30＋31＋32＋33 repository.

## Results

### Skill structure

- Batch 33 skills discovered: **20/20**
- Skill names unique: **20/20**
- Required front matter (`name`, `description`): passed
- Required sections (`Workflow`, `Verification`, `Stop and escalate when`, `Definition of done`): passed
- Skill number range: **1223–1242**

### Schemas and templates

- JSON Schema files: **8**
- Template JSON files: **11**
- Draft 2020-12 schema meta-validation: passed
- Template-to-schema validation: passed
- JSON syntax validation: passed

### Python and shell validation

- Batch 33 Python scripts compile: passed
- Batch 33 test module compiles: passed
- `install.sh` shell syntax: passed
- Installer merge behavior with existing `AGENTS.md` and `Makefile`: passed

### Batch 33 toolkit tests

```text
test_skill_bundle                              passed
test_schemas_and_templates                     passed
test_scaffold_and_validate                     passed
test_graph_validators_reject_unknown_refs      passed
test_candidate_scoring                         passed
test_conservative_gate_rejects_fake_certification passed
test_validator_rejects_auto_approve            passed
```

Total: **7/7 passed**.

### Security and conservative-gate negative checks

Verified that the toolkit rejects or blocks:

- forged `certified` status without evidence;
- missing Holdout and Representative Workload corpora;
- missing runtime and IaC source-map coverage;
- missing Plan, Apply/Emulator, P0 runtime, security, drift, cost, rollback and destroy evidence;
- dangling IaC IR dependency references;
- unattended `-auto-approve` commands;
- broad default egress and disabled encryption patterns in target profiles;
- unset ownership, state locking, encryption, exact versions, regions or account models.

### Merged repository regression

The merged repository contains **102 Codex Skills** across Batch 29–33.

The following suites were run separately and passed:

```text
Batch 29 toolkit: 3/3
Batch 30 toolkit: 3/3
Batch 31 toolkit: 5/5
Batch 32 toolkit: 6/6
Batch 33 toolkit: 7/7
```

### Installer validation

Installed the Batch 33 overlay into a temporary repository that already contained `AGENTS.md` and `Makefile`.

Verified:

- Skills copied to `.agents/skills/b33-*`;
- Batch 33 docs, schemas, templates, scripts, and tests copied;
- `AGENTS.md` appended without overwriting existing content;
- `Makefile.batch33` installed and included;
- installed skill bundle validated successfully.

## Environment limitations

The current execution environment does **not** contain the following external tools:

```text
terraform / tofu
kubectl
helm
docker / podman
aws
az
gcloud
```

Therefore this validation did not execute real Terraform plans/applies, Kubernetes server-side validation, Helm rendering against a cluster, cloud provisioning, CI/CD runs, or cloud runtime drift checks. Those are deliberately treated as route-specific certification evidence and are required by the generated Skills and conservative Gate before a Cloud Pack can become `certified`.

## Conclusion

The Batch 33 package is structurally valid, installable, testable, and conservative against false certification. It is ready to direct Codex implementation in a repository with the required IaC tools, cloud accounts, clusters, state backends, CI/CD environments, and approved isolated test resources.
