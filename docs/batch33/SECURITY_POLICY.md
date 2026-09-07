
# Security and data-boundary policy

- Default deny network egress and ingress; justify every public endpoint.
- Preserve least privilege and workload identity. Do not replace scoped roles with broad account credentials.
- Use secret references and ephemeral credentials. Never render secret values into plans, state, CI logs, manifests, or artifacts.
- Encrypt state, backups, logs, queues, databases, and object stores according to classification.
- Preserve tenant, account, subscription, project, namespace, and environment boundaries.
- Verify software supply chain: signed images, pinned actions, modules, charts, SBOM, provenance, and vulnerability evidence.
- Validate deletion, retention, residency, backup, restore, audit, and break-glass behavior.
- Model-generated IaC or policy is a candidate and must pass deterministic checks and real sandbox validation.
