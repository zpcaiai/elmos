# ELMOS release deployment

Repository-owned implementation of the pinned release/deployment specification.
See [implementation and exact coverage](../../docs/release-deployment/IMPLEMENTATION.md).

```powershell
uv run --no-project --with cryptography==46.0.7 --with jsonschema==4.25.1 --with temporalio==1.32.0 python tooling/validate_release_deployment.py
```

Install this project on an approved Linux deployment host to expose the
`elmos-deployment-agent` entry point. It will fail closed until the root-owned trust
configuration, signed permit, canonical Compose/config bytes and secret mounts
have been provisioned by the host. No cloud operation or daemon starts on import.

The package currently contains a locally tested deployment core, optional Temporal
adapter, host-mountable API, provider request adapters, remote agent and P1/P2
planning/validation components. Host application wiring and live acceptance are
separate remaining work; local qualification is not full product completion.
