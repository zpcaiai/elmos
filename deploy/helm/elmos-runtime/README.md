# ELMOS runtime chart

This is a repository-owned deployment template for the production-runtime
kernel. Images must be immutable reviewed digests, and the database secret and
database/provider CIDRs are environment-owned values. The chart intentionally
does not create credentials, grant database roles, or authorize a production
deployment.

The worker is a StatefulSet behind a headless Service so the endpoint registry
can address an individual worker. The default network policy is deny-by-default;
operators must provide the exact database and provider CIDRs before rendering.
