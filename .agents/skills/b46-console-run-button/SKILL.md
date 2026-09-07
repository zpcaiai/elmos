---
name: b46-console-run-button
description: Wire the one-click run button into the ELMOS Web Console so a recipient can start a generated project on a 10 minute free lease, watch the countdown, extend explicitly, and read the reclamation report and retained evidence.
---

## Operating mode

Work in the repository. Read the shared Batch 46 contracts before editing:

- `../../../docs/batch46/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch46/RUNTIME_LEASE_POLICY.md`
- `../../../docs/batch46/CONSOLE_RUN_BUTTON.md`
- `../../../docs/batch46/QUALITY_GATES.md`

Console surfaces live in `apps/web-console`:

- `app/lib/smokeContracts.ts` — shared types
- `app/lib/server/smokeLeaseRunner.ts` — session lifecycle
- `app/api/smoke/*` — REST entries
- `app/components/SmokeRunButton.tsx` — the button panel
- `app/smoke/page.tsx` — standalone page

## Global constraints

- The button starts the pack's own vendored runner. It never reimplements lease,
  seeding, assertion or teardown logic — a second implementation is a second
  set of bugs and a guaranteed divergence from the CLI.
- The free quota is a ceiling the client cannot raise. A request may shorten the
  lease; it may never lengthen it except through an explicit, attributable extension.
- Availability is reported, never assumed. An execution location or entry that
  is not configured renders as `NOT_CONFIGURED` / `unavailable` with its reason.
- `NOT_RUN` is displayed as `NOT_RUN`. It is never rolled into a pass, and never
  hidden because the panel looks nicer without it.
- The countdown renders locally but the deadline is always the server's
  `expiresAtEpoch`, re-synced on every poll.
- Services are reclaimed at expiry; evidence is not. Result and gate conclusion
  stay reachable, while the Console exposes bounded log tails and their original
  byte counts; full local logs remain in the project runtime when no rerun has
  archived them.

## Skill 4616: Console one-click run button

## Use this skill when

- A generation or conversion surface needs a run button on its completion view.
- The hosted runner, local execution or lease policy configuration changed.
- A recipient reports that the button appeared available but the run failed.

## Risks and invariants

- A button that looks available but cannot run spends the recipient's first
  impression and their trust; availability must come from evidence.
- Holding the run's lifetime in the request or in the browser means a console
  restart or a closed tab orphans a live service — the runner must be detached
  and the watchdog must own reclamation.
- An extension granted in the UI but not honoured by the running watchdog is
  worse than no extension: the operator believes they have time they do not have.
- Showing only the primary check turns a partial run into an apparent pass.

## Workflow

1. Read capability and pack summary before rendering; disable the button with a
   stated reason when either says no.
2. Choose the execution location by availability — hosted first because the
   recipient needs no toolchain, local second because it is closer to real use.
3. Start the run detached, with the free quota as the ttl, and persist the
   session under the runtime state directory keyed to the tenant.
4. Poll the pack's own `smoke/runtime/status.json` for live state; poll
   `result.json`, `lease.json` and `gate-result.json` for outcome.
5. Require reason and actor for extension, surface `billableSeconds`, and audit
   the extension through the business audit wrapper.
6. On expiry, render the reclamation report — processes stopped, whether any was
   killed after the grace period, containers and volumes removed, ephemeral data
   deleted, residue or none — and keep the evidence reachable.
7. Offer a fresh run rather than an implicit renewal once the quota is spent.

## Required outputs

- `/api/smoke/capability`, `/api/smoke/pack`, `/api/smoke/sessions` and the
  session `extend`, `stop` and `evidence` entries
- a reusable `SmokeRunButton` that any completion view can render with one line
- a session record per run, tenant-scoped and path-confined

## Verification

- `pnpm --filter @elmos/web-console exec tsc --noEmit` is clean.
- A run started from the button survives a console restart and is still reclaimed
  on time.
- An extension granted in the UI moves the deadline of the *running* instance,
  not merely the lease file.
- An extension without a reason is rejected end to end.
- With no execution location configured, the button is disabled and states why.

## Stop and escalate when

- A hosted runner implementation cannot honour the same quota and teardown rules.
- Anyone asks for an auto-renewing or unbounded session.
- A completion view wants to show a pass without an executed run behind it.
