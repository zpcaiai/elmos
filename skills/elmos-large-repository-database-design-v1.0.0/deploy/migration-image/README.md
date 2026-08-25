# Elmos Migration Image

Build from the repository root:

```bash
docker build \
  -f deploy/migration-image/Dockerfile \
  --build-arg FLYWAY_BASE_IMAGE=redgate/flyway:11-alpine \
  -t ghcr.io/your-org/elmos-migrate:1.1.0 .
```

Production requirements:

- pin `FLYWAY_BASE_IMAGE` by immutable digest;
- sign the resulting image;
- generate SBOM and vulnerability report;
- use a dedicated migrator Secret/role;
- allow network access only to PostgreSQL;
- write `ops.migration_run` and preserve migration output as an Artifact;
- run `database/tests/invariants.sql` through the deployment-verifier after migration;
- never enable Flyway clean in production.
