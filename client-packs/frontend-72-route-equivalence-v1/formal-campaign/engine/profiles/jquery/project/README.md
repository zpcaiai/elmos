# ELMOS 有界导航验证

This project was generated from typed UI Interaction IR for the directional route `angular@22.0.8 -> jquery`.

## Generated scope

- Exact target profile, build configuration, application shell, routes, accessibility semantics, UI IR snapshot, CI workflow, and fail-closed verification script.
- Source business behavior was not executed by the static generator.
- Dependency lock resolution, target build/startup, browser or device journeys, visual parity, accessibility review, holdout execution, signing, and release remain `NOT_RUN`.

## Next commands

For npm targets, materialize an exact lock without lifecycle scripts:

```bash
npm install --package-lock-only --ignore-scripts --no-audit --no-fund
bash scripts/verify.sh
```

Flutter and HarmonyOS targets require their exact declared SDK Runner. The verification script fails closed when that Runner or required evidence is absent.

## Open obligations

- Resolve and review an immutable dependency lock with an approved network and supply-chain policy.
- Build and start the generated target with the exact target profile.
- Replay route, state, action, effect, form, API, permission, localization, error, and business contracts.
- Run keyboard/focus or native accessibility, semantic-tree, contrast, zoom/text-scale, and assistive-technology checks.
- Capture approved visual baselines without automatic updates or widened masks.
- Run physically separate negative, holdout, and representative journey corpora.
- Bind raw runtime evidence to the exact source snapshot, target artifact, environment, executor, and independent verifier.
- Implement and independently verify identity, tenant, authorization, session expiry, and permission-denied journeys.
- Verify every declared deep link from cold start, warm start, background, invalid input, and unsupported-version states.
- Obtain explicit legacy-target approval, maintenance owner, security exception, and dated exit criteria.
