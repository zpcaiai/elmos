# FRT external evidence runbook

This workflow makes the remaining gates executable without allowing repository
content, an agent, or a local JSON edit to manufacture independent evidence.
The real trust store, private keys, customer workspaces, devices and production
credentials stay outside the repository.

## Security and authority boundary

- The accountable approver signs an exact, expiring run authorization before
  execution. It pins the check, environment, Runner capability, purpose,
  evidence root and parameters.
- `ELMOS_FRT_EXTERNAL_RUNNER` points to an independently administered executable
  implementing `elmos.external-runner.v1`. Repository and customer content never
  select a shell command.
- The external Runner enforces its sandbox, approved network targets, secret
  references, write roots, cleanup and provider/device permissions.
- Raw customer source, credentials, tokens, device identifiers and personal
  data are not copied into repository evidence. Only minimized manifests,
  digests, redacted results and accountable decisions are allowed.
- Executor, verifier and approver sign the same canonical record. Executor and
  verifier must be different people and organizations; the approver cannot be
  the executor.

## Generate and preflight the exact cases

The checked-in generator owns 15 exact cases and maps them to the nine
authoritative external checks. Adapter IDs are allowlisted identities, not
commands. Generation and preflight do not download browsers, run customer code,
authorize production, or upgrade evidence state.

```sh
python3 scripts/frt/external_qualification.py generate
python3 scripts/frt/external_qualification.py preflight
python3 scripts/frt/external_qualification.py exercise
python3 scripts/frt/external_qualification.py check
python3 scripts/frt/external_qualification.py check-preflight
python3 scripts/frt/external_qualification.py check-execution
```

`preflight` launches Firefox/WebKit only when their exact managed executable is
already installed, probes hvigor without invoking a build, counts only
non-placeholder approved/holdout files, and records the availability of the
external Runner and privacy-minimized device candidate. Missing prerequisites
become typed blockers. Every case remains `NOT_RUN`,
`production_operation_authorized=false`, and `NOT_CERTIFIED` even when its local
toolchain is available.

`exercise` dispatches all 15 case IDs through an explicit allowlisted Python
adapter registry. It checks the managed-browser launch boundary, hvigor
evidence boundary, immutable visual-baseline policy, manual AT and physical
device templates, and the nine typed external-campaign contracts. The emitted
local-execution report is SHA-bound to the exact plan and preflight. A passed
adapter code contract is not an external execution result.

Run the repository-side integrity suite separately:

```sh
cd scripts/frt
python3 -m unittest \
  test_external_campaign_parameters.py \
  test_external_evidence.py \
  test_external_qualification.py \
  test_run_frt_gate.py -v
```

Those signed fixtures prove that the protocol accepts exact records and rejects
tampering for all nine checks. They are local tests and must never be installed
under `certification/external-evidence/` as real campaign results.

## Privacy-minimized local iOS execution candidate

An authorized local install/launch rehearsal may be normalized only with the v2
recorder. Keep the raw `devicectl` device list, install, launch and process JSON
plus the device-ID file under a disposable temporary root; never place them in
the repository. Supply an external, non-persisted HMAC key:

```sh
ELMOS_FRT_DEVICE_ID_HMAC_KEY="$EPHEMERAL_DEVICE_KEY" \
node scripts/frt/record_frt_ios_device_evidence.mjs \
  --project /private/.../disposable-flutter-project \
  --devices-json /private/.../devices.json \
  --device-id-file /private/.../device-id.txt \
  --install-json /private/.../install.json \
  --launch-json /private/.../launch.json \
  --processes-json /private/.../processes.json
```

The recorder verifies physical-device reality, a signed `Runner.app`, the exact
bundle identifier and a live launched process. It persists no device name,
alias, raw identifier, raw process ID or command output. Its maximum state is
`PASSED_LOCAL_EVIDENCE_ONLY`; P0 journeys, manual visual/AT review, the signed
device matrix and customer acceptance remain `NOT_RUN`.

## One-by-one workflow

1. Create an approved check-specific parameters JSON outside customer source.
   It contains exact commits, targets, devices, workloads, scopes or journeys
   and secret reference names, never secret values.
   Inspect and validate the exact closed contract before requesting a signature:

   ```sh
   python3 scripts/frt/external_campaign_parameters.py contract --check performance
   python3 scripts/frt/external_campaign_parameters.py validate \
     --check performance --parameters /approved/parameters.json
   ```

   Unknown fields, raw commands, scope widening, stale plan/case/adapter
   bindings, arbitrary secret values and weakened check-specific minimums are
   rejected before authorization can be prepared.
2. Prepare an unsigned authorization under the run evidence directory:

   ```sh
   python3 scripts/frt/external_evidence.py prepare \
     --check performance \
     --purpose "independent representative performance qualification" \
     --environment qualified-runner-01 \
     --approver product-owner-01 \
     --approver-organization owner-organization \
     --parameters /approved/parameters.json \
     --output client-packs/frt-g01-g30-platform/certification/external-evidence/run-001/authorization.json
   ```

3. The approver reviews the scope and signs with an external private key:

   ```sh
   python3 scripts/frt/external_evidence.py sign \
     --kind authorization --role APPROVER \
     --document client-packs/frt-g01-g30-platform/certification/external-evidence/run-001/authorization.json \
     --private-key /secure/approver-private.pem --key-id approver-key-01
   ```

4. Dispatch only after the configured trust store accepts the authorization:

   ```sh
   ELMOS_FRT_EXTERNAL_RUNNER=/approved/bin/elmos-frt-external-runner \
   python3 scripts/frt/external_evidence.py dispatch \
     --authorization client-packs/frt-g01-g30-platform/certification/external-evidence/run-001/authorization.json \
     --trust-store /approved/frt-trust-store.json \
     --output client-packs/frt-g01-g30-platform/certification/external-evidence/run-001/record.json
   ```

5. The Runner preserves every evidence role in
   `external-evidence-profile.json`. It emits a `PASSED` record only when all
   frozen metrics and claims pass; failed or inconclusive output cannot promote.
6. Executor, independent verifier and approver inspect and sign the record, in
   that order, with `sign --kind record` and separate keys.
7. Verify, then bind:

   ```sh
   python3 scripts/frt/external_evidence.py verify \
     --record client-packs/frt-g01-g30-platform/certification/external-evidence/run-001/record.json \
     --trust-store /approved/frt-trust-store.json

   python3 scripts/frt/external_evidence.py bind \
     --record client-packs/frt-g01-g30-platform/certification/external-evidence/run-001/record.json \
     --trust-store /approved/frt-trust-store.json
   ```

8. Run both authorities with the same trust store:

   ```sh
   python3 scripts/frt/run_frt_gate.py \
     client-packs/frt-g01-g30-platform/certification/frt-gate-request.json \
     --external-trust-store /approved/frt-trust-store.json
   python3 scripts/batch32/run_client_gate.py client-packs/frt-g01-g30-platform
   ```

## Check ownership

| FRT check | Runner capability | Cannot be replaced by |
|---|---|---|
| `real_source_target_builds` | `FRT_REAL_CUSTOMER_ROUTE_CAMPAIGN` | generated Counter fixtures |
| `device_matrix` | `FRT_PHYSICAL_DEVICE_VISUAL_AT_MATRIX` | emulation, Axe, or unapproved screenshots |
| `independent_holdout` | `FRT_INDEPENDENT_HOLDOUT_CAMPAIGN` | development or locally authored fixtures |
| `formal_proof` | `FRT_BOUNDED_FORMAL_PROOF` | tests, coverage, or solver invocation without replay |
| `performance` | `FRT_REPRESENTATIVE_PERFORMANCE_CAMPAIGN` | one local navigation timing |
| `chaos_dr` | `FRT_AUTHORIZED_CHAOS_DR_DRILL` | unit backup/restore tests |
| `penetration_test` | `FRT_AUTHORIZED_PENETRATION_ASSESSMENT` | dependency audit or automated scan alone |
| `production_observation` | `FRT_AUTHORIZED_PRODUCTION_OBSERVATION` | local logs or synthetic telemetry |
| `customer_acceptance` | `FRT_INDEPENDENT_CUSTOMER_ACCEPTANCE` | agent, developer, or synthetic approval |

Until a real record completes this workflow, its check remains `NOT_RUN`;
production operations remain unauthorized and production remains
`NOT_CERTIFIED`.
