# Java Control Plane on Google Cloud Run

This directory binds the production Java Control Plane to the exact Google
Cloud project `nexus` (`gen-lang-client-0684615336`) in `asia-east1`. The
deployment remains digest-pinned and sends database values only to Google
Secret Manager over stdin. It never writes a credential into a command,
receipt, Git file, image label, or Cloud Run environment variable.

The Vercel setting is a server-only HTTPS origin:

```text
ELMOS_CONTROL_PLANE_BASE_URL=https://elmos-control-plane-<provider-id>.asia-east1.run.app
```

Do not append `/api`, `/actuator`, a query, credentials, or a trailing path.
The Web Console adds the exact API and readiness paths itself. Production
rejects HTTP and conflicting legacy `CONTROL_PLANE_BASE_URL` values.

## Deploy

Pull the already-provisioned Vercel production environment into an owner-only
temporary file. The deployment parser reads only the six allowlisted Neon and
Descope keys and never evaluates shell syntax.

```bash
umask 077
vercel env pull /private/tmp/elmos-vercel-production.env \
  --environment=production --yes \
  --cwd apps/web-console

python scripts/deploy/control_plane_cloud_run.py validate
python scripts/deploy/control_plane_cloud_run.py plan \
  --expected-revision "$(git rev-parse HEAD)"
python scripts/deploy/control_plane_cloud_run.py \
  --gcloud-config-dir /private/tmp/elmos-gcloud-auth apply \
  --vercel-env-file /private/tmp/elmos-vercel-production.env \
  --expected-revision "$(git rev-parse HEAD)"
```

`apply` refuses dirty tracked files, a revision mismatch, malformed provider
configuration, missing Google identity, non-digest images, URL injection, or
missing Secret Manager input. It creates only the exact Artifact Registry,
runtime service account, three secrets, and Cloud Run service described in
`profile.json`. The public Cloud Run invoker is intentional because Vercel
must reach the service; Spring Security still verifies Descope issuer, JWKS,
audience, expiry, signature, subject, tenant, role, and permission on protected
routes. Actuator health is the only anonymous application endpoint.

After readiness returns `UP`, bind the returned HTTPS origin to Vercel and
redeploy the Web Console:

```bash
printf '%s' "$ELMOS_CONTROL_PLANE_BASE_URL" | \
  vercel env add ELMOS_CONTROL_PLANE_BASE_URL production \
  --cwd apps/web-console --scope zpchoney-6160s-projects
vercel deploy --prod --cwd apps/web-console --scope zpchoney-6160s-projects
```

## Rollback

The rollback command moves 100% traffic to the previous existing revision; it
does not rebuild, mutate secrets, or delete resources:

```bash
python scripts/deploy/control_plane_cloud_run.py \
  --gcloud-config-dir /private/tmp/elmos-gcloud-auth rollback
```

Resource deletion is deliberately not automated. It needs an explicit owner,
retention decision, database migration check, and post-delete orphan audit.
