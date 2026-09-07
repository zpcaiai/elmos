# External validation runbook

This runbook prepares evidence collection; it does not mark any external
activity as complete.

1. Freeze the exact Web Console commit, generated artifact digests, browser and
   assistive-technology versions, operating systems, locale, viewport and
   rootless Runner configuration.
2. Assign an executor and verifier who did not implement the journey. Record
   authorization, purpose, environment and test-data classification.
3. Execute every journey in `external-validation-plan.json` without changing
   the UI, accessibility rules, test thresholds or security policy during the
   run.
4. Store raw transcripts, screenshots, issue logs and decisions outside the
   source tree, then bind their byte counts and SHA-256 digests in the approved
   evidence store.
5. Leave failed, skipped, inaccessible and incomplete journeys non-passing.
   Remediate through a new build and repeat the affected independent run.
6. Run the Batch 32 validator and gate only after all required evidence is
   available. The gate result, not this template, determines readiness.

Current assistive-technology review, independent user acceptance and external
conformance status is `NOT_RUN`.
