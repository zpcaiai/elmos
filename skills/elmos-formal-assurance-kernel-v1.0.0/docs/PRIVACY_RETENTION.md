# Privacy, Data Classification and Retention

## Data classes

- Public: published formal examples and common rule certificates.
- Internal: package configuration and noncustomer metrics.
- Confidential: customer source maps, formulas, models and reports.
- Restricted: secrets accidentally captured, production snapshots, personal data and security counterexamples.

## Collection minimization

Store hashes and source locations instead of complete source where possible. Solver inputs may still encode source semantics and are therefore confidential. Metrics never carry formula or SQL text.

## Retention

| Artifact | Default |
|---|---|
| transient solver workspace | delete after committed evidence |
| raw logs | short standard retention, redacted |
| proof certificates/models | audit retention while release is supported |
| counterexamples | audit retention; restricted if they contain data |
| waivers/gate decisions | audit plus regulatory/business requirement |
| legal hold | immutable until explicitly released |

## Deletion

Tenant deletion must account for legal hold and active release evidence. Deleting proof evidence may revoke a `TRUSTED` claim. Cryptographic erasure uses tenant-scoped KMS keys where applicable.
