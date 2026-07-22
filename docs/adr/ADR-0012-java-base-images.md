# ADR-0012: Java sandbox base images

Status: Accepted

## Decision

ELMOS maintains separate Java 8, 11, 17, and 21 sandbox definitions. Base images and runtime selection are digest-pinned; an image is selectable only after smoke tests, SBOM, vulnerability/provenance evidence, and explicit digest approval.

## Consequences

Mutable tags and locally built but unapproved images cannot run customer code. Build credentials use temporary BuildKit mounts, never layers or build args.
