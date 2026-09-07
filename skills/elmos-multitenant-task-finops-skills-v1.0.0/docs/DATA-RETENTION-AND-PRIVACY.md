# Data Retention, Export, and Privacy

## Storage principle

PostgreSQL stores authoritative metadata, state, hashes, bounded JSON, ledger rows, and object references. Large user inputs, outputs, checkpoints, and verbose logs live in tenant-scoped encrypted object storage. This avoids database bloat while retaining complete lineage.

## Retention classes

Retention is policy-versioned by tenant and data class. Financial ledgers normally outlive operational logs. Legal hold overrides deletion. A task export contains manifests and authorized object payloads but never exposes secrets or another tenant's data.

## Deletion workflow

1. Resolve tenant/account authorization and legal holds.
2. Freeze a deletion manifest and affected object list.
3. Tombstone searchable projections.
4. Delete eligible objects and verify absence.
5. Delete or anonymize eligible relational records in dependency order.
6. Preserve mandatory financial/audit records under the applicable policy.
7. Emit a signed deletion evidence record.

## Sensitive input policy

Classify every input and output as public, internal, confidential, or restricted. Redact credentials before persistence. Store secret references only when a task needs a leased credential; never archive the plaintext secret as task input.
