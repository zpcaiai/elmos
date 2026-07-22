---
name: java-sandbox-image-builder
description: Build or review pinned Java sandbox images for ELMOS. Use for Java 8, 11, 17, or 21 build images, image manifests, SBOM/provenance, digest approval, or container-image CI.
---

# Java Sandbox Image Builder

Build minimal, reproducible Java toolchain images. An image becomes runnable only after its digest and evidence have been approved.

## Required workflow

1. Pin every base image by immutable digest.
2. Install only the declared JDK/build tools and create a fixed non-root user.
3. Keep credentials out of Dockerfiles, build args, environment layers, and build logs; use BuildKit secret mounts when access is required.
4. Generate an SBOM, vulnerability report, build provenance, smoke-test result, and final image digest.
5. Register compatibility metadata for Java version and Maven/Gradle support.
6. Mark the digest approved only when all mandatory evidence policies pass.

## Non-negotiable boundaries

- Tags are display metadata, not runtime identity.
- No package-manager caches, compilers, or network tools beyond the declared profile.
- No root default user and no embedded SCM or repository credentials.
- An unbuilt, unscanned, unsigned, or unapproved image cannot be selected by workspace provisioning.

## Acceptance checks

- CI proves the configured uid is non-root and the declared Java version runs.
- The image manifest records base/final digests and evidence references.
- Secret scanning finds no injected sentinel in image history or layers.
- Live image availability is reported separately from source-level Dockerfile validation.

