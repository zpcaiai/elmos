# syntax=docker/dockerfile:1.7
ARG FLYWAY_BASE_IMAGE=redgate/flyway:11-alpine
FROM ${FLYWAY_BASE_IMAGE}

LABEL org.opencontainers.image.title="Elmos Database Migration"
LABEL org.opencontainers.image.description="Versioned PostgreSQL migrations for the Elmos large-repository execution data plane"

COPY database/migrations/ /flyway/sql/

# The base image entrypoint is `flyway`; Helm/Compose supplies `migrate`.
CMD ["migrate"]
