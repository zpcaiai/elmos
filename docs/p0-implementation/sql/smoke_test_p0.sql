-- Executable acceptance rehearsal for V52/V53/V54.
-- Run against a database that already has V1..V54 applied.
-- Every RAISE EXCEPTION below is a real assertion: the script fails loudly.

\set ON_ERROR_STOP on
BEGIN;

-- ---------------------------------------------------------------------------
-- Fixture: two accounts, two organizations, active CNY subscriptions
-- ---------------------------------------------------------------------------

INSERT INTO accounts (account_id, status, display_name, primary_email, email_verified_at)
VALUES ('acc-alice', 'ACTIVE', 'Alice', 'alice@example.com', now()),
       ('acc-bob',   'ACTIVE', 'Bob',   'bob@example.com',   now());

SELECT elmos_provision_organization('org-a', 'Tenant A', 'acc-alice', 'actor-alice', 'cn-north');
SELECT elmos_provision_organization('org-b', 'Tenant B', 'acc-bob',   'actor-bob',   'cn-north');

INSERT INTO subscriptions (
    subscription_id, organization_id, schema_version, status, idempotency_key, payload,
    catalog_version, plan_id, actor_id, billing_period, currency, price_minor,
    current_period_start, current_period_end
) VALUES
 ('sub-a', 'org-a', '2.0', 'ACTIVE', 'sub-a', '{}'::jsonb,
  '2026-07-28.2', 'elmos-pro-monthly', 'actor-alice', 'MONTH', 'CNY', 12900,
  now() - interval '1 day', now() + interval '29 days'),
 ('sub-b', 'org-b', '2.0', 'ACTIVE', 'sub-b', '{}'::jsonb,
  '2026-07-28.2', 'elmos-free-trial', 'actor-bob', 'TRIAL', 'CNY', 0,
  now() - interval '1 day', now() + interval '6 days');

DO $$
BEGIN
    -- elmos-pro-monthly declares concurrent_job_limit 3, elmos-free-trial 1.
    IF elmos_execution_concurrency_limit('org-a') <> 3 THEN
        RAISE EXCEPTION 'ASSERT_FAILED: org-a concurrency limit should follow the CNY plan catalog, got %',
            elmos_execution_concurrency_limit('org-a');
    END IF;
    IF elmos_execution_concurrency_limit('org-b') <> 1 THEN
        RAISE EXCEPTION 'ASSERT_FAILED: org-b trial concurrency limit wrong';
    END IF;
    -- Fail closed: an organization with no active period schedules nothing.
    IF elmos_execution_concurrency_limit('org-system') <> 0 THEN
        RAISE EXCEPTION 'ASSERT_FAILED: unsubscribed organization must be 0';
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Fixture: one attested runner in the shared pool
-- ---------------------------------------------------------------------------

INSERT INTO runner_pools (runner_pool_id, organization_id, schema_version, status, idempotency_key, payload)
VALUES ('pool-shared', 'org-system', '2.0', 'ACTIVE', 'pool-shared', '{}'::jsonb);

INSERT INTO runner_nodes (
    runner_node_id, organization_id, schema_version, status, idempotency_key, payload,
    runner_pool_ref, agent_version, fleet_status, capabilities, max_concurrency,
    rootless_attested, readonly_root_attested, capability_drop_attested,
    network_default_deny_attested, attestation_verified_at, attestation_verifier_actor_id,
    image_allowlist_version, last_heartbeat_at
) VALUES (
    'runner-1', 'org-system', '2.0', 'ACTIVE', 'runner-1', '{}'::jsonb,
    'pool-shared', '0.1.0', 'READY', ARRAY['generation:multi'], 4,
    true, true, true, true, now(), 'actor-platform-sre', 'allow-2026-07-28', now()
);

-- A node that has not attested cannot become READY at all.
DO $$
BEGIN
    BEGIN
        INSERT INTO runner_nodes (
            runner_node_id, organization_id, schema_version, status, idempotency_key, payload,
            runner_pool_ref, agent_version, fleet_status, capabilities, max_concurrency
        ) VALUES (
            'runner-bad', 'org-system', '2.0', 'ACTIVE', 'runner-bad', '{}'::jsonb,
            'pool-shared', '0.1.0', 'READY', ARRAY['generation:multi'], 4
        );
        RAISE EXCEPTION 'ASSERT_FAILED: an unattested runner reached READY';
    EXCEPTION WHEN check_violation THEN
        NULL; -- expected
    END;
END;
$$;

-- ---------------------------------------------------------------------------
-- Enqueue, including idempotency and the mutable-tag ban
-- ---------------------------------------------------------------------------

SELECT elmos_enqueue_execution_job(
    'job-a1', 'org-a', 'actor-alice', 'GENERATION', 'project-synthesis',
    'idem-a1', repeat('a', 64), '{"targets":["java"]}'::jsonb, 'generation:multi',
    'registry.example.com/elmos/generation@sha256:' || repeat('b', 64),
    100::smallint, 1800, 1::smallint);

DO $$
DECLARE v_id varchar;
BEGIN
    -- Same key, same digest: idempotent replay returns the original job.
    v_id := elmos_enqueue_execution_job(
        'job-a1-dup', 'org-a', 'actor-alice', 'GENERATION', 'project-synthesis',
        'idem-a1', repeat('a', 64), '{"targets":["java"]}'::jsonb, 'generation:multi',
        NULL, 100::smallint, 1800, 1::smallint);
    IF v_id <> 'job-a1' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: idempotent replay returned %', v_id;
    END IF;

    -- Same key, different digest: conflict, never a silent overwrite.
    BEGIN
        PERFORM elmos_enqueue_execution_job(
            'job-a1-conflict', 'org-a', 'actor-alice', 'GENERATION', 'project-synthesis',
            'idem-a1', repeat('c', 64), '{}'::jsonb, 'generation:multi',
            NULL, 100::smallint, 1800, 1::smallint);
        RAISE EXCEPTION 'ASSERT_FAILED: idempotency conflict was not detected';
    EXCEPTION WHEN sqlstate 'P0001' THEN
        IF SQLERRM NOT LIKE '%IDEMPOTENCY_CONFLICT%' THEN RAISE; END IF;
    END;

    -- A mutable image tag must be impossible to store.
    BEGIN
        PERFORM elmos_enqueue_execution_job(
            'job-a-mutable', 'org-a', 'actor-alice', 'GENERATION', 'project-synthesis',
            'idem-mutable', repeat('d', 64), '{}'::jsonb, 'generation:multi',
            'registry.example.com/elmos/generation:latest', 100::smallint, 1800, 1::smallint);
        RAISE EXCEPTION 'ASSERT_FAILED: a mutable runner image tag was accepted';
    EXCEPTION WHEN check_violation THEN
        NULL; -- expected
    END;
END;
$$;

-- Four more org-a jobs and two org-b jobs, to exercise fairness and quota.
SELECT elmos_enqueue_execution_job('job-a' || i, 'org-a', 'actor-alice', 'GENERATION',
        'project-synthesis', 'idem-a' || i, md5(i::text) || md5(i::text), '{}'::jsonb,
        'generation:multi', NULL, 100::smallint, 1800, 1::smallint)
  FROM generate_series(2, 5) AS i;
SELECT elmos_enqueue_execution_job('job-b' || i, 'org-b', 'actor-bob', 'GENERATION',
        'project-synthesis', 'idem-b' || i, md5('b' || i) || md5('b' || i), '{}'::jsonb,
        'generation:multi', NULL, 100::smallint, 1800, 1::smallint)
  FROM generate_series(1, 2) AS i;

-- ---------------------------------------------------------------------------
-- Claim: per-tenant concurrency caps and fairness
-- ---------------------------------------------------------------------------

CREATE TEMP TABLE claimed AS
SELECT * FROM elmos_claim_execution_jobs(
    'runner-1', ARRAY['generation:multi'], 4, 120,
    ARRAY['lease-1', 'lease-2', 'lease-3', 'lease-4'],
    ARRAY[repeat('1', 64), repeat('2', 64), repeat('3', 64), repeat('4', 64)]);

DO $$
DECLARE v_a integer; v_b integer; v_total integer;
BEGIN
    SELECT count(*) INTO v_total FROM claimed;
    SELECT count(*) INTO v_a FROM claimed WHERE organization_id = 'org-a';
    SELECT count(*) INTO v_b FROM claimed WHERE organization_id = 'org-b';

    -- org-a is capped at 3 by its plan, org-b at 1. A single runner with
    -- capacity 4 must therefore land exactly 3 + 1, never 4 + 0.
    IF v_a <> 3 THEN RAISE EXCEPTION 'ASSERT_FAILED: org-a claimed % (plan cap is 3)', v_a; END IF;
    IF v_b <> 1 THEN RAISE EXCEPTION 'ASSERT_FAILED: org-b claimed % (trial cap is 1)', v_b; END IF;
    IF v_total <> 4 THEN RAISE EXCEPTION 'ASSERT_FAILED: total claimed %', v_total; END IF;

    -- One tenant cannot starve the other: the noisy tenant queued 5, the quiet
    -- one queued 2, and the quiet one still got scheduled in the same pass.
    IF NOT EXISTS (SELECT 1 FROM claimed WHERE organization_id = 'org-b') THEN
        RAISE EXCEPTION 'ASSERT_FAILED: fairness ordering starved the smaller tenant';
    END IF;
END;
$$;

-- A second claim on a saturated fleet returns nothing rather than over-admitting.
DO $$
DECLARE v_more integer;
BEGIN
    SELECT count(*) INTO v_more FROM elmos_claim_execution_jobs(
        'runner-1', ARRAY['generation:multi'], 2, 120,
        ARRAY['lease-5', 'lease-6'], ARRAY[repeat('5', 64), repeat('6', 64)]);
    IF v_more <> 0 THEN RAISE EXCEPTION 'ASSERT_FAILED: runner over-admitted % jobs', v_more; END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Heartbeat, cancel propagation, completion
-- ---------------------------------------------------------------------------

DO $$
DECLARE v_job varchar; v_lease varchar; v_hash varchar; v_cancel boolean;
BEGIN
    SELECT job_id, lease_id INTO v_job, v_lease FROM claimed WHERE organization_id = 'org-a' LIMIT 1;
    v_hash := (SELECT token_sha256 FROM runner_job_leases WHERE runner_job_lease_id = v_lease);

    SELECT cancel_requested INTO v_cancel FROM elmos_heartbeat_execution_lease(
        v_lease, 'runner-1', v_hash, 'building', 40::smallint, '{"unit":7}'::jsonb, 120);
    IF v_cancel THEN RAISE EXCEPTION 'ASSERT_FAILED: unexpected cancel signal'; END IF;

    IF (SELECT status FROM execution_jobs WHERE job_id = v_job) <> 'RUNNING' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: heartbeat did not move CLAIMED to RUNNING';
    END IF;
    IF (SELECT checkpoint_cursor->>'unit' FROM execution_jobs WHERE job_id = v_job) <> '7' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: checkpoint was not persisted';
    END IF;

    -- A stolen or forged credential cannot drive somebody else's lease.
    BEGIN
        PERFORM elmos_heartbeat_execution_lease(v_lease, 'runner-1', repeat('f', 64),
            'building', 41::smallint, NULL, 120);
        RAISE EXCEPTION 'ASSERT_FAILED: forged lease token was accepted';
    EXCEPTION WHEN sqlstate 'P0001' THEN
        IF SQLERRM NOT LIKE '%CREDENTIAL_MISMATCH%' THEN RAISE; END IF;
    END;

    -- Cancel requested by the user reaches the runner on its next heartbeat.
    PERFORM elmos_request_execution_cancel('org-a', v_job, 'actor-alice');
    SELECT cancel_requested INTO v_cancel FROM elmos_heartbeat_execution_lease(
        v_lease, 'runner-1', v_hash, 'building', 45::smallint, NULL, 120);
    IF NOT v_cancel THEN RAISE EXCEPTION 'ASSERT_FAILED: cancel did not propagate to the runner'; END IF;

    PERFORM elmos_complete_execution_job(v_lease, 'runner-1', v_hash, 'CANCELLED', 'BLOCKED', NULL);
    IF (SELECT status FROM execution_jobs WHERE job_id = v_job) <> 'CANCELLED' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: completion did not record CANCELLED';
    END IF;

    -- Terminal states are immutable even for a direct UPDATE.
    BEGIN
        UPDATE execution_jobs SET status = 'SUCCEEDED' WHERE job_id = v_job;
        RAISE EXCEPTION 'ASSERT_FAILED: a terminal job was rewritten';
    EXCEPTION WHEN sqlstate 'P0001' THEN
        IF SQLERRM NOT LIKE '%TERMINAL_IMMUTABLE%' THEN RAISE; END IF;
    END;
END;
$$;

-- ---------------------------------------------------------------------------
-- Runner loss: the reaper requeues instead of losing the job
-- ---------------------------------------------------------------------------

DO $$
DECLARE v_job varchar; v_lease varchar; v_reaped integer;
BEGIN
    SELECT job_id, lease_id INTO v_job, v_lease
      FROM claimed WHERE organization_id = 'org-b' LIMIT 1;

    UPDATE execution_jobs SET max_attempts = 3 WHERE job_id = v_job;
    UPDATE execution_job_dispatch SET lease_expires_at = now() - interval '1 minute'
     WHERE job_id = v_job;

    v_reaped := elmos_reap_execution_leases();
    IF v_reaped < 1 THEN RAISE EXCEPTION 'ASSERT_FAILED: reaper found no expired lease'; END IF;

    IF (SELECT status FROM execution_jobs WHERE job_id = v_job) <> 'QUEUED' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: a job whose runner died was not requeued';
    END IF;
    IF (SELECT lease_state FROM runner_job_leases WHERE runner_job_lease_id = v_lease) <> 'EXPIRED' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: the dead lease was not expired';
    END IF;
END;
$$;

-- Counters must survive the whole sequence without drifting.
DO $$
DECLARE v_fixed integer;
BEGIN
    v_fixed := elmos_reconcile_dispatch_counters();
    IF v_fixed <> 0 THEN
        RAISE EXCEPTION 'ASSERT_FAILED: dispatch counters drifted, % rows corrected', v_fixed;
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Identity: last-owner protection, invitation flow
-- ---------------------------------------------------------------------------

DO $$
DECLARE v_org varchar;
BEGIN
    BEGIN
        UPDATE organization_memberships SET member_role = 'MEMBER'
         WHERE organization_id = 'org-a' AND account_ref = 'acc-alice';
        RAISE EXCEPTION 'ASSERT_FAILED: the last owner was demoted';
    EXCEPTION WHEN sqlstate 'P0001' THEN
        IF SQLERRM NOT LIKE '%LAST_OWNER_PROTECTED%' THEN RAISE; END IF;
    END;

    INSERT INTO organization_invitations (
        invitation_id, organization_id, channel, destination_hmac, destination_display,
        member_role, token_sha256, invited_by_actor_id, expires_at
    ) VALUES (
        'inv-1', 'org-a', 'SMS', repeat('e', 64), '138****8888', 'MEMBER',
        repeat('9', 64), 'actor-alice', now() + interval '7 days'
    );

    v_org := elmos_accept_organization_invitation(repeat('9', 64), 'acc-bob', 'actor-bob-in-a');
    IF v_org <> 'org-a' THEN RAISE EXCEPTION 'ASSERT_FAILED: invitation acceptance returned %', v_org; END IF;
    IF NOT EXISTS (
        SELECT 1 FROM organization_memberships
         WHERE organization_id = 'org-a' AND account_ref = 'acc-bob' AND member_state = 'ACTIVE'
    ) THEN
        RAISE EXCEPTION 'ASSERT_FAILED: invited member is not active';
    END IF;

    -- The same token cannot be replayed.
    BEGIN
        PERFORM elmos_accept_organization_invitation(repeat('9', 64), 'acc-bob', 'actor-bob-in-a');
        RAISE EXCEPTION 'ASSERT_FAILED: an accepted invitation was replayed';
    EXCEPTION WHEN sqlstate 'P0001' THEN
        IF SQLERRM NOT LIKE '%NOT_PENDING%' THEN RAISE; END IF;
    END;
END;
$$;

-- ---------------------------------------------------------------------------
-- Object storage: fail closed until verified, retention from the plan catalog
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    BEGIN
        UPDATE object_storage_backends
           SET backend_state = 'ACTIVE', endpoint = 'https://oss-cn-beijing.example.com',
               bucket = 'elmos-artifacts'
         WHERE backend_id = 'primary';
        RAISE EXCEPTION 'ASSERT_FAILED: a backend went ACTIVE without credentials or encryption';
    EXCEPTION WHEN check_violation THEN
        NULL; -- expected
    END;

    UPDATE object_storage_backends
       SET backend_state = 'ACTIVE',
           endpoint = 'https://oss-cn-beijing.example.com',
           bucket = 'elmos-artifacts',
           credential_reference = 'secret://elmos/oss/primary',
           server_side_encryption = 'SSE_KMS',
           cmk_reference = 'kms://cn-north/elmos-artifacts',
           verified_at = now(),
           verified_by_actor_id = 'actor-platform-sre'
     WHERE backend_id = 'primary';
END;
$$;

DO $$
DECLARE v_job varchar; v_expires timestamptz; v_days integer;
BEGIN
    SELECT job_id INTO v_job FROM execution_jobs
     WHERE organization_id = 'org-a' AND status <> 'CANCELLED' LIMIT 1;

    INSERT INTO content_objects (
        content_object_id, organization_id, content_sha256, byte_size, media_type,
        backend_id, storage_key, object_state
    ) VALUES (
        'obj-1', 'org-a', repeat('7', 64), 4096, 'application/zip',
        'primary', 'org-a/obj/' || repeat('7', 64), 'PENDING_UPLOAD'
    );

    -- Publishing before the server has verified the stored bytes is refused.
    BEGIN
        PERFORM elmos_publish_job_artifact('art-1', 'org-a', v_job, 'PROJECT_ARCHIVE',
            'project.zip', 'obj-1', 'STANDARD');
        RAISE EXCEPTION 'ASSERT_FAILED: an unverified object was published';
    EXCEPTION WHEN sqlstate 'P0001' THEN
        IF SQLERRM NOT LIKE '%NOT_VERIFIED%' THEN RAISE; END IF;
    END;

    UPDATE content_objects
       SET object_state = 'AVAILABLE', uploaded_at = now(), verified_at = now()
     WHERE content_object_id = 'obj-1';

    PERFORM elmos_publish_job_artifact('art-1', 'org-a', v_job, 'PROJECT_ARCHIVE',
        'project.zip', 'obj-1', 'STANDARD');

    -- elmos-pro-monthly declares artifact_retention_days 30.
    v_days := elmos_effective_retention_days('org-a', 'STANDARD');
    IF v_days <> 30 THEN RAISE EXCEPTION 'ASSERT_FAILED: retention should follow the plan, got %', v_days; END IF;

    SELECT expires_at INTO v_expires FROM job_artifacts WHERE artifact_id = 'art-1';
    IF v_expires IS NULL OR v_expires < now() + interval '29 days' THEN
        RAISE EXCEPTION 'ASSERT_FAILED: artifact expiry not derived from the plan';
    END IF;

    -- A download grant may not outlive fifteen minutes.
    BEGIN
        INSERT INTO artifact_download_grants (grant_id, organization_id, artifact_id, actor_id, expires_at)
        VALUES ('grant-bad', 'org-a', 'art-1', 'actor-alice', now() + interval '2 hours');
        RAISE EXCEPTION 'ASSERT_FAILED: a long-lived presigned grant was accepted';
    EXCEPTION WHEN check_violation THEN
        NULL; -- expected
    END;

    PERFORM elmos_issue_download_grant('grant-1', 'org-a', 'art-1', 'actor-alice', 300);
    IF NOT EXISTS (SELECT 1 FROM artifact_download_grants WHERE grant_id = 'grant-1') THEN
        RAISE EXCEPTION 'ASSERT_FAILED: download grant was not audited';
    END IF;
END;
$$;

-- Legal hold beats retention.
DO $$
DECLARE v_expired integer;
BEGIN
    UPDATE job_artifacts SET expires_at = NULL, legal_hold = true WHERE artifact_id = 'art-1';
    v_expired := elmos_expire_artifacts('gc-1', 100);
    IF (SELECT deleted_at FROM job_artifacts WHERE artifact_id = 'art-1') IS NOT NULL THEN
        RAISE EXCEPTION 'ASSERT_FAILED: a legally held artifact was expired';
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Tenant isolation still holds for every new tenant-scoped table
-- ---------------------------------------------------------------------------

DO $$
DECLARE v_missing text;
BEGIN
    SELECT string_agg(t.tablename, ', ') INTO v_missing
      FROM (VALUES
            ('execution_jobs'), ('execution_job_events'), ('content_objects'),
            ('job_artifacts'), ('artifact_download_grants'), ('object_retention_policies'),
            ('organization_invitations'), ('organization_api_keys'),
            ('organization_sso_connections'), ('organization_lifecycle_requests')
           ) AS t(tablename)
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_policies p
         WHERE p.schemaname = 'public' AND p.tablename = t.tablename AND p.policyname = 'tenant_isolation'
     );
    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION 'ASSERT_FAILED: tables without tenant_isolation: %', v_missing;
    END IF;

    SELECT string_agg(c.relname, ', ') INTO v_missing
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relname IN ('execution_jobs', 'execution_job_events', 'content_objects', 'job_artifacts')
       AND NOT c.relforcerowsecurity;
    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION 'ASSERT_FAILED: tables without FORCE ROW LEVEL SECURITY: %', v_missing;
    END IF;
END;
$$;

ROLLBACK;
\echo 'P0 SMOKE TEST PASSED'
