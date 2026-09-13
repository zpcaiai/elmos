# Ethan external certification protocol

This protocol separates repository engineering from independent certification.
The repository prepares a request and verifies a response; it never generates,
receives, imports, or uses Ethan's private key.

## 1. Release Control prepares the request

After the implementation commit is pushed, Release Control runs:

```sh
python3 scripts/certification/ethan_external_exchange.py prepare \
  --target-sha <full-40-hex-sha> \
  --remote-ref origin/<protected-candidate-ref> \
  --repository-url https://github.com/zpcaiai/elmos.git \
  --requester-actor-id <actor> \
  --requester-organization-id <organization> \
  --output <new-directory-outside-the-repository>
```

The request binds the exact commit, Git tree, challenge, six in-scope business
lines, commands, external evidence classes, and portable Runner bytes. M29 is
explicitly excluded. Release Control communicates `request.digest` to Ethan
through an authenticated channel separate from the request bundle.

## 2. Ethan creates and holds the replacement key externally

Ethan should use an HSM/KMS where possible. If an owner-only OpenSSL key is used,
it must be created on Ethan-controlled storage outside every ELMOS checkout:

```sh
umask 077
openssl genpkey -algorithm ED25519 -out <ethan-controlled-private-key-path>
openssl pkey -in <ethan-controlled-private-key-path> -pubout -out <public-key-path>
openssl pkey -pubin -in <public-key-path> -outform DER | openssl dgst -sha256
```

Only the public key may enter the response exchange. Ethan communicates the
canonical `sha256:<64 lowercase hex>` fingerprint through an authenticated
channel independent from Git, pull requests, CI artifacts, and the response
bundle. The private key must never be passed to any repository script.

## 3. Ethan checks out and executes the exact SHA independently

Ethan clones from the authenticated remote, fetches the exact SHA, checks out a
detached HEAD, verifies a clean tree, reviews the request and portable runner,
then runs `external_runner.py` in an independently controlled environment. The
runner accepts only the request's fixed `make <target>` argv arrays, never uses a
shell, captures stdout/stderr, hashes all evidence, and never reads a private key.

All external evidence classes in
`external-certification-plan.json` need real, non-synthetic files. The evidence
index is a JSON object keyed by business-line ID and evidence class, with
absolute Ethan-side paths as values. Missing evidence remains `NOT_RUN` and the
runner returns `BLOCKED`.

```sh
python3 external_runner.py \
  --request <request.json> \
  --expected-request-digest sha256:<digest-from-independent-channel> \
  --checkout <detached-clean-checkout> \
  --public-key <public-key-path> \
  --evidence-index <evidence-index.json> \
  --output <new-external-output-directory> \
  --environment-id <independent-environment-id> \
  --provider <provider> \
  --region <region> \
  --executor-actor-id <actor> \
  --executor-organization-id <organization> \
  --confirm-independent \
  --confirm-private-key-external
```

## 4. Ethan reviews and signs outside the runner

The unsigned response is expected to remain `BLOCKED` until every required real
evidence item exists and all commands pass. Ethan reviews the exact bytes, then
signs without exposing the key to repository code:

```sh
openssl pkeyutl -sign \
  -inkey <ethan-controlled-private-key-path> \
  -rawin \
  -in <response.unsigned.json> \
  -out <response.sig>
```

Ethan returns the public key, `response.unsigned.json`, `response.sig`, and the
complete response directory. The fingerprint still arrives separately.

## 5. Release Control verifies but does not self-certify

```sh
python3 scripts/certification/ethan_external_exchange.py verify-response \
  --request <request.json> \
  --response <response.unsigned.json> \
  --signature <response.sig> \
  --public-key <ethan-public-key.pem> \
  --expected-fingerprint sha256:<fingerprint-from-independent-channel>
```

A successful result is `READY_FOR_DOMAIN_GATES / NOT_CERTIFIED`. It proves the
signature, fingerprint match, exact-SHA binding, evidence byte integrity, scope,
role separation, and replay result structure. It does not prove that a channel
was authentic or that evidence claims are semantically true. Release Control
must authenticate the separate channel, and each business-line gate must inspect
the real evidence and independently decide whether its own status can advance.

Any missing, changed, expired, synthetic, same-actor, same-organization,
repository-controlled, dirty-worktree, wrong-SHA, wrong-tree, wrong-fingerprint,
wrong-signature, partial-scope, or non-zero command result fails closed.
