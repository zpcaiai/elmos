# ELMOS air-gapped deployment boundary

An air-gapped installation imports one signed release bundle into a local staging registry, verifies checksums, signature, SBOM, provenance and malware-scan evidence, then promotes only approved artifacts. Runtime access to Maven Central, GitHub, public model providers, public telemetry, license servers, CDNs, external fonts and scripts is forbidden.

Use `elmosctl preflight`, then `import-bundle`, `install`, `verify`, `backup` and a restore drill. Mutating commands require both `--evidence-approved` and `--confirm`; the CLI still delegates actual installation to an approved customer environment and never reports the external action as complete itself.

The local environment must provide OCI and Recipe registries, Maven mirror, vulnerability database snapshot, IdP, Secret Provider, signing trust roots, backup target and optional private model. With no model, health checks, deterministic OpenRewrite and independent validation remain available while repair is manual.
