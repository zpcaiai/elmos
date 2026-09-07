# ELMOS database and Big Data bounded runtime

This repository-owned runtime binds all 46 exact database and Big Data Skills
to conservative plan-skeleton entry points. It validates the shape of
caller-supplied tenant, project, actor, request, and idempotency identifiers;
emits canonical, digest-bound skeletons; and makes all 554 stable task IDs plus
their missing evidence gates explicit. Those context values are
`CALLER_ASSERTED_UNVERIFIED`, and idempotency is digest binding only: there is
no authentication binding or replay store.

It deliberately performs no database, provider, connector, network, build,
deployment, benchmark, chaos, repair, cutover, or certification operation. A
plan skeleton is not a generated plan, whole-Skill implementation, or runtime
evidence. Every result therefore retains `DECLARED`, `NOT_RUN`, and
`NOT_CERTIFIED` claims and reports the source tasks themselves as `NOT_RUN`.

The runtime never imports or executes code from the attached source package.
It binds to the independently generated repository manifest under
`docs/database-bigdata-skills/` and fails closed on catalog drift. The console
authoritative CLI is invoked directly, before package import:

```sh
python3 -I -S -B engines/database-bigdata-engine/launcher.py catalog
python3 -I -S -B engines/database-bigdata-engine/launcher.py run < request.json
```

That package-external launcher rejects bytecode caches, checks every engine
source file against the manifest, and loads package modules only from those
verified bytes. The process retains that byte snapshot and rejects
repository drift before and after every dispatch. The checked-in
manifest and reviewed launcher remain repository trust roots; this local byte
check is not a signature or independent supply-chain attestation. Direct Python
library imports are for already-trusted code and explicitly report
`DIRECT_IMPORT_TRUSTED_CODE_ONLY`; only the isolated command above reports the
launcher's verified-source pre-import boundary.
