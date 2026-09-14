#!/usr/bin/env bash
set -euo pipefail

# Deterministic Elmos bootstrap template.
# Inputs are non-secret references/identifiers supplied by the executor.
: "${ELMOS_DEPLOYMENT_ID:?}"
: "${ELMOS_IMAGE_REF:?}"   # must include @sha256:...
: "${ELMOS_CONTAINER_NAME:?}"
: "${ELMOS_PORT_MAP:?}"

if [[ "${ELMOS_IMAGE_REF}" != *@sha256:* ]]; then
  echo "refusing non-digest image" >&2
  exit 41
fi

previous="$(docker inspect --format='{{.Config.Image}}' "${ELMOS_CONTAINER_NAME}" 2>/dev/null || true)"
printf '%s' "$previous" > "/var/lib/elmos/${ELMOS_DEPLOYMENT_ID}.previous-image"

docker pull "${ELMOS_IMAGE_REF}"
docker rm -f "${ELMOS_CONTAINER_NAME}.candidate" >/dev/null 2>&1 || true

docker run -d \
  --name "${ELMOS_CONTAINER_NAME}.candidate" \
  --restart unless-stopped \
  -p "${ELMOS_PORT_MAP}" \
  "${ELMOS_IMAGE_REF}"

# Activation/health/rollback orchestration is controlled by Elmos workflow,
# not inferred from this script.
