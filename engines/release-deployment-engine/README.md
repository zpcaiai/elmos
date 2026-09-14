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

The package includes the deployment core, optional Temporal adapter, Spring/WSGI
signed host bridge, remote agent, bounded Alibaba RPC and Kubernetes HTTPS
transports, ALB/DNS/Kubernetes execution controllers and remaining P1/P2 planners.
Canonical policy/session/evidence wiring and the remaining coverage matrix entries
still require implementation; local qualification is not full product completion.
