# Git repository workspaces

ELMOS can create a bounded local workspace from GitHub, Gitee, or another
HTTPS Git server. The workspace is resolved to an advertised exact commit
before checkout and can inventory, read, and modify UTF-8 text files including:

- source code and tests;
- Markdown and other documentation;
- YAML, JSON, TOML, XML, properties, and similar configuration;
- Docker and Compose local deployment files;
- GitHub Actions, GitLab CI, Kubernetes, Helm, and Terraform cloud deployment
  files.

The current boundary ends at a local diff. Creating a workspace or saving a
file does **not** push, open a pull request, merge, invoke a provider API, or
deploy anything. Those effects require a separate, explicitly authorized
delivery workflow.

## Safety contract

- Clone URLs must be credential-free HTTPS. `file:` URLs exist only behind the
  disabled-by-default local development flag.
- GitHub and Gitee selections require the exact `github.com` and `gitee.com`
  hosts. Self-hosted services use `GENERIC_GIT` and must be present in the
  exact server-side host allowlist; wildcards are not accepted.
- Requested refs are resolved through advertised heads/tags and bound to an
  exact 40-character commit. The fetched commit must match.
- Symbolic links, non-regular files, binary data, secret-shaped files,
  `.git/**`, and `ownership/policy.json` are not editable.
- Every changed path must be listed in `approvedPaths`. Existing files also
  require their previously read SHA-256 digest, preventing silent concurrent
  overwrite.
- A detected `CODEOWNERS` file requires explicit owner approval. Repositories
  with submodules or Git LFS declarations remain read-only until those objects
  receive separate authorization, hydration, and digest verification.
- Repository and file counts are bounded. Credentials are ephemeral and are
  neither written to Git configuration nor stored in workspace metadata.
- Total workspace count is bounded and expired workspaces are removed after
  the configured TTL; corrupt or unknown directories are never auto-deleted.
- Each API attempt and completion/failure is written to the tenant-isolated
  user activity log without repository content, clone URLs, file paths, or
  credentials.

## Control-plane configuration

Set the following server-side values:

```text
ELMOS_REPOSITORY_WORKSPACE_ENABLED=true
ELMOS_REPOSITORY_WORKSPACE_API_KEY=<at least 24 characters>
ELMOS_REPOSITORY_WORKSPACE_ROOT=/absolute/bounded/workspace/path
ELMOS_REPOSITORY_CREDENTIAL_ROOT=/absolute/owner-only/credential/path
ELMOS_REPOSITORY_WORKSPACE_MAX_FILES=100000
ELMOS_REPOSITORY_WORKSPACE_MAX_BYTES=2147483648
ELMOS_REPOSITORY_ALLOWED_GENERIC_HOSTS=git.example.com,git.internal.example
ELMOS_REPOSITORY_WORKSPACE_MAX_COUNT=1000
ELMOS_REPOSITORY_WORKSPACE_TTL_HOURS=168
```

The Web Console additionally needs:

```text
ELMOS_REPOSITORY_WORKSPACE_BASE_URL=https://control-plane.example
ELMOS_REPOSITORY_WORKSPACE_API_KEY=<same internal key>
ELMOS_REPOSITORY_WORKSPACE_TENANT_ID=<trusted tenant>
ELMOS_REPOSITORY_WORKSPACE_ACTOR_ID=<trusted actor>
ELMOS_REPOSITORY_WORKSPACE_USER_TOKEN=<browser/session gate, at least 24 characters>
```

The browser never receives the internal repository key or Git credential.
Production should provide the user gate through the existing `__Host-` session
cookie. The explicit bearer-token field in the current console is intended for
controlled environments until the product identity provider is connected.

## Private repositories

A request may refer to a server-side credential by a safe identifier such as
`customer-a-gitee`. The credential root then contains
`customer-a-gitee.credential`, owned and readable only by the service account:

```text
git-username
provider-token-or-password
```

Never commit this file, put the token in a clone URL, or expose the reference
directory through the Web Console. Credential files are read per operation,
copied into an `EphemeralCredential`, cleared after JGit returns, and never
persisted in the workspace.

## API surface

All control-plane calls require the internal repository key plus trusted
organization and actor headers.

- `GET /api/v1/repository-workspaces/capabilities`
- `POST /api/v1/repository-workspaces`
- `GET /api/v1/repository-workspaces/{workspaceId}`
- `GET /api/v1/repository-workspaces/{workspaceId}/files?path=...`
- `POST /api/v1/repository-workspaces/{workspaceId}/changes`
- `DELETE /api/v1/repository-workspaces/{workspaceId}`

An apply request is explicit:

```json
{
  "baseCommit": "40-character source commit",
  "intent": "Human-readable requested change",
  "codeOwnerApproval": false,
  "approvedPaths": ["README.md"],
  "changes": [
    {
      "operation": "UPSERT",
      "path": "README.md",
      "expectedSha256": "digest returned by the read endpoint",
      "contentBase64": "base64-encoded UTF-8 text"
    }
  ]
}
```

The result exposes `pushed=false`, `pullRequestCreated=false`, and
`deployed=false` so downstream callers cannot confuse a local edit with remote
delivery.

The Web Console displays the opaque workspace UUID and provides an
identity-bound recovery field. Refreshing the browser does not persist a Git
credential or browser token; the user re-enters the short-lived token and
recovers the UUID, while the control plane rechecks both tenant and actor.
