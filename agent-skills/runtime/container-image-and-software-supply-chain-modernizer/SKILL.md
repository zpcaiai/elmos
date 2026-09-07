---
name: container-image-and-software-supply-chain-modernizer
description: Modernize traditional processes into reproducible, non-root, signed, scanned OCI images with explicit state, signal, architecture, SBOM, provenance, and supply-chain gates. Use for container readiness and image artifacts.
---

# Container Supply Chain Modernizer

## Container workflow

1. Inventory process, ports, files, state, user, signals, working directory, temp, locale, timezone, certificates, native libraries, kernel needs, capabilities, devices, cron, children, and init behavior.
2. Classify readiness as ready, ready with external state/compatibility, requires refactor, Windows-required, privileged-required, or not containerizable.
3. Choose process splitting, temporary supervisor, sidecar, init container, or keep-VM explicitly.
4. Verify PID 1 behavior, child reaping, SIGTERM, draining, in-flight work, transactions, queue handling, file flush, and shutdown timeout.
5. Classify files as immutable, temporary, cache, persistent, shared, secret, or log; externalize persistent state and prefer a read-only root filesystem.
6. Build with a fixed base digest, multi-stage definition, minimal packages, non-root user, no secret/key/cache residue, and target-architecture validation.
7. Bind source commit, build definition, builder identity, dependency hashes, SBOM, license result, vulnerability result, signature, provenance, and image digest.

Do not publish a multi-architecture manifest until every advertised architecture passes. Privileged, host-network, root, device, kernel, local-state, static-hostname, signal, unsupported-base, secret-layer, and architecture findings must remain explicit gates.

