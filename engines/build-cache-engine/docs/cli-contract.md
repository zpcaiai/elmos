# CLI Contract

Recommended commands:

```text
elmos cache status
elmos cache inspect <action-key>
elmos cache explain-miss <run-id> <node-id>
elmos cache verify [--project <id>] [--deep]
elmos cache pin <artifact-or-tree>
elmos cache unpin <pin-id>
elmos cache gc --dry-run
elmos cache gc --apply <plan-id>
elmos workspace list
elmos workspace inspect <run-id>
elmos workspace recover <run-id>
elmos workspace quarantine <run-id> <staged-file-id>
elmos run resume <run-id>
elmos run pause <run-id>
elmos run cancel <run-id>
elmos artifact materialize <digest> <destination>
elmos doctor cache
```

Defaults are non-destructive and project-scoped. Commands that mutate state require explicit scope, expected version or lease where applicable, and an idempotency key.
