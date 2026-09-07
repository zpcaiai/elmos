package io.elmos.persistence;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.Set;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers(disabledWithoutDocker = true)
class FlywayMigrationTest {
    private static final Set<String> BATCH_14_TABLES = Set.of(
            "growth_programs", "growth_goals", "north_star_metrics", "metric_definitions",
            "growth_events", "identity_links", "funnels", "journeys", "experiments",
            "experiment_variants", "experiment_assignments", "experiment_results",
            "channels", "campaigns", "touchpoints", "attribution_models", "attribution_results",
            "content_pillars", "content_topics", "content_assets", "content_versions",
            "content_reviews", "seo_keywords", "seo_pages", "events", "event_attendees",
            "developer_profiles", "api_applications", "sdk_usage", "cli_usage",
            "sample_repositories", "sandbox_sessions", "community_spaces", "community_members",
            "community_posts", "community_answers", "community_reputation", "community_badges",
            "moderation_cases", "community_events", "marketplace_publishers", "marketplace_assets",
            "asset_versions", "asset_certifications", "asset_installations", "asset_usage",
            "asset_reviews", "asset_reports", "marketplace_orders", "publisher_payouts",
            "marketplace_bounties", "locales", "translation_keys", "translations",
            "translation_memories", "terminology", "localization_projects", "regional_requirements",
            "regions", "regional_launches", "regional_prices", "regional_partners",
            "regional_campaigns", "regional_metrics", "growth_playbooks", "growth_learnings",
            "growth_risks", "growth_costs", "growth_economics");

    @Container static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:17.5-alpine");
    @Test void createsAllAuthoritativeSchemasThroughProductBatchThirtyEightAndMigrationPackAdmission() {
        // defaultSchema is pinned because this database moves out from under an
        // unpinned Flyway mid-run. PostgreSQL's default search_path is
        // "$user", public; the container's user is named "test"; and V45 creates
        // a product schema that is also named "test". Before the migration that
        // schema does not exist, so Flyway resolves its history table to public
        // -- but every later resolution picks the now-existing "test" schema,
        // finds no history there, and reports all 53 migrations still pending.
        // The migrate() call was never the problem; the second reading was
        // looking at a different table than the first wrote to.
        var flyway=Flyway.configure().dataSource(POSTGRES.getJdbcUrl(),POSTGRES.getUsername(),POSTGRES.getPassword()).defaultSchema("public").load();
        // Asserting a literal migration count would fail on every new migration and
        // invite whoever sees the red to bump the number, which teaches nothing.
        // What actually matters is that the set on disk and the set applied agree:
        // everything discovered runs, and nothing is left pending afterwards. That
        // survives growth and still catches a migration that silently fails to
        // resolve. The floor keeps a deletion from passing quietly.
        int discovered = flyway.info().pending().length;
        assertTrue(discovered >= 51,
                () -> "expected at least the 51 migrations that existed when this "
                        + "invariant was written, found " + discovered);
        assertEquals(discovered, flyway.migrate().migrationsExecuted,
                "every migration resolved on an empty database must be applied");
        assertEquals(0, flyway.info().pending().length,
                "no migration may remain pending after a full migrate");
        var dataSource = new org.springframework.jdbc.datasource.DriverManagerDataSource(
                POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
        var jdbc=org.springframework.jdbc.core.simple.JdbcClient.create(dataSource);
        verifyPlatformAdminIdentityBoundary(jdbc);
        verifyPlatformAdminConcurrentWriteOrder(dataSource, jdbc);
        verifyRuntimeRoleUsesFunctionsButCannotBypassPlatformAdminBoundary(dataSource, jdbc);
        assertEquals(1, jdbc.sql("""
                SELECT count(*) FROM flyway_schema_history
                 WHERE version = '63' AND success
                """).query(Integer.class).single(),
                "V63 must be recorded as successfully executed by Flyway");
        String executionBusinessLineConstraint = jdbc.sql("""
                SELECT pg_get_constraintdef(c.oid)
                  FROM pg_constraint c
                  JOIN pg_class t ON t.oid = c.conrelid
                  JOIN pg_namespace n ON n.oid = t.relnamespace
                 WHERE n.nspname = 'public'
                   AND t.relname = 'execution_jobs'
                   AND c.conname = 'execution_jobs_business_line'
                """).query(String.class).single();
        assertTrue(executionBusinessLineConstraint.contains("MODERNIZATION_PROOF"),
                "V63 must admit the modernization proof business line");
        assertTrue(executionBusinessLineConstraint.contains("GENERATION")
                        && executionBusinessLineConstraint.contains("TRANSLATION")
                        && executionBusinessLineConstraint.contains("SPRING_UPGRADE")
                        && executionBusinessLineConstraint.contains("REPOSITORY_WORKSPACE"),
                "V63 must preserve every business line admitted before V63");
        assertTrue(jdbc.sql("select count(*) from information_schema.tables where table_schema='public'").query(Integer.class).single() >= 1240);
        assertEquals(1, jdbc.sql("select count(*) from information_schema.tables where table_schema='public' and table_name='github_app_onboarding_states'").query(Integer.class).single());
        assertEquals(1, jdbc.sql("select count(*) from pg_policies where schemaname='public' and tablename='github_app_onboarding_states' and policyname='github_app_onboarding_tenant_isolation'").query(Integer.class).single());
        assertEquals(12, jdbc.sql("select count(*) from information_schema.columns where table_schema='public' and table_name='audit_events' and column_name in ('organization_id','event_kind','business_line','route','target','session_id','duration_ms','error_code','metric_name','metric_value','metadata','received_at')").query(Integer.class).single());
        assertEquals(1, jdbc.sql("select count(*) from pg_trigger where tgname='audit_events_append_only' and not tgisinternal").query(Integer.class).single());
        assertEquals(8, jdbc.sql("select count(*) from information_schema.tables where table_schema='public' and table_name in ('product_telemetry_events','operations_slo_policies','operations_alerts','operations_incidents','operations_remediation_proposals','operations_workflow_events','operations_notification_outbox','operations_retention_runs')").query(Integer.class).single());
        assertEquals(8, jdbc.sql("select count(*) from pg_policies where schemaname='public' and tablename in ('product_telemetry_events','operations_slo_policies','operations_alerts','operations_incidents','operations_remediation_proposals','operations_workflow_events','operations_notification_outbox','operations_retention_runs') and policyname='tenant_isolation'").query(Integer.class).single());
        assertEquals(56, jdbc.sql("select count(*) from information_schema.tables where table_schema='public' and table_name in ('recipe_execution_manifests','repair_tasks','validation_decisions','delivery_snapshots','organizations','authorization_decisions','runner_job_leases','audit_events','entitlements','orders','project_status_snapshots','support_tickets','dotnet_solutions','msbuild_evaluations','dotnet_fingerprints','roslyn_symbols','dotnet_migration_plans','aspnet_inventories','wcf_services','ef_contexts','dotnet_compatibility_results','python_projects','python_environment_snapshots','python_symbols','python_migration_plans','django_applications','data_pipelines','ml_model_artifacts','system_landscapes','system_dependency_edges','api_contracts','message_contracts','contract_consumer_matrix','composite_migration_plans','compatibility_windows','data_ownership_records','shadow_experiments','traffic_shift_plans','system_cutover_plans','decommission_plans','client_applications','frontend_workspaces','frontend_routes','visual_baselines','accessibility_findings','client_release_plans','database_estates','database_objects','sql_workloads','schema_conversions','bulk_load_runs','data_quality_results','lakehouse_tables','semantic_metrics','lineage_events','governance_policies')").query(Integer.class).single());
        assertEquals(16, jdbc.sql("select count(*) from information_schema.tables where table_schema='public' and table_name in ('infrastructure_estates','physical_hosts','workloads','firewall_rules','storage_volumes','middleware_instances','workload_placement_decisions','container_images','kubernetes_clusters','serverless_functions','infrastructure_plans','observability_profiles','cost_allocations','chaos_experiments','portability_profiles','infrastructure_cutover_plans')").query(Integer.class).single());
        assertEquals(24, jdbc.sql("select count(*) from information_schema.tables where table_schema='public' and table_name in ('security_estates','security_assets','security_boundaries','security_identities','access_policies','cryptographic_assets','security_requirements','security_controls','control_assessments','software_components','sbom_documents','provenance_statements','vex_statements','security_tools','security_scans','security_findings','vulnerabilities','vulnerability_exposures','runtime_security_events','data_processing_activities','threat_models','compliance_catalogs','oscal_assessment_results','authorization_boundaries')").query(Integer.class).single());
        assertEquals(24, jdbc.sql("select count(*) from information_schema.tables where table_schema='public' and table_name in ('test_estates','test_framework_profiles','test_suites','test_cases','test_case_identities','test_executions','test_results','test_discovery_snapshots','quality_requirements','quality_risks','quality_coverage_records','test_portfolios','characterization_scenarios','golden_masters','contract_tests','provider_verifications','property_tests','mutation_runs','test_data_assets','test_environments','ai_test_candidates','flaky_test_profiles','quality_decisions','continuous_validation_runs')").query(Integer.class).single());
        assertTrue(jdbc.sql("select count(*) from pg_policies where schemaname='public' and policyname='tenant_isolation'").query(Integer.class).single() >= 1239);
        var publicTables = Set.copyOf(jdbc.sql("select table_name from information_schema.tables where table_schema='public'").query(String.class).list());
        var missingBatch14Tables = BATCH_14_TABLES.stream().filter(table -> !publicTables.contains(table)).sorted().toList();
        assertEquals(69, BATCH_14_TABLES.size());
        assertTrue(missingBatch14Tables.isEmpty(), () -> "Missing Batch 14 tables: " + missingBatch14Tables);
        assertEquals(81, jdbc.sql("select count(*) from information_schema.tables where table_schema='software_delivery'").query(Integer.class).single());
        assertEquals(107, jdbc.sql("select count(*) from information_schema.tables where table_schema='ai_platform'").query(Integer.class).single());
        assertEquals(112, jdbc.sql("select count(*) from information_schema.tables where table_schema='edge_industrial'").query(Integer.class).single());
        assertEquals(108, jdbc.sql("select count(*) from information_schema.tables where table_schema='operations_sre'").query(Integer.class).single());
        assertEquals(108, jdbc.sql("select count(*) from information_schema.tables where table_schema='enterprise_architecture'").query(Integer.class).single());
        assertEquals(516, jdbc.sql("select count(*) from pg_policies where schemaname in ('software_delivery','ai_platform','edge_industrial','operations_sre','enterprise_architecture') and policyname='tenant_isolation'").query(Integer.class).single());
        assertEquals(104, jdbc.sql("select count(*) from information_schema.tables where table_schema='technology_business_management'").query(Integer.class).single());
        assertEquals(110, jdbc.sql("select count(*) from information_schema.tables where table_schema='organization_workforce'").query(Integer.class).single());
        assertEquals(104, jdbc.sql("select count(*) from information_schema.tables where table_schema='transformation_execution'").query(Integer.class).single());
        assertEquals(132, jdbc.sql("select count(*) from information_schema.tables where table_schema='autonomous_control_tower'").query(Integer.class).single());
        assertEquals(20, jdbc.sql("select count(*) from information_schema.tables where table_schema='mvp_engineering'").query(Integer.class).single());
        assertEquals(12, jdbc.sql("select count(*) from information_schema.tables where table_schema='mvp_gap_review'").query(Integer.class).single());
        assertEquals(16, jdbc.sql("select count(*) from information_schema.tables where table_schema='secure_java_vertical'").query(Integer.class).single());
        assertEquals(166, jdbc.sql("select count(*) from information_schema.tables where table_schema='identity_access_governance'").query(Integer.class).single());
        assertEquals(6, jdbc.sql("select count(*) from information_schema.tables where table_schema='migration_pack_certification'").query(Integer.class).single());
        assertEquals(664, jdbc.sql("select count(*) from pg_policies where schemaname in ('technology_business_management','organization_workforce','transformation_execution','autonomous_control_tower','mvp_engineering','mvp_gap_review','secure_java_vertical','identity_access_governance') and policyname='tenant_isolation'").query(Integer.class).single());
        String productSchemas = "'scm','catalog','delivery','workspace','execution','sandbox','artifact','evidence','attestation','signing','provenance','sbom','oci','verification','retention','privacy','analytics','assurance','risk','control','audit','portfolio','cockpit','forecast','performance','security','test','policy','authorization','deployment','runtime','admission','remediation','policy_decision','policy_rollout','cache','transfer','operations'";
        assertEquals(1426, jdbc.sql("select count(*) from information_schema.tables where table_schema in (" + productSchemas + ")").query(Integer.class).single());
        assertEquals(10, jdbc.sql("""
                select count(*)
                  from information_schema.columns
                 where table_schema = 'artifact'
                   and table_name = 'artifacts'
                   and column_name in ('id','tenant_id','project_id','job_id','work_item_id',
                                       'artifact_type','object_uri','sha256','size_bytes','created_at')
                """).query(Integer.class).single(),
                "V77 must own the canonical artifact.artifacts runtime shape");
        assertEquals(16, jdbc.sql("""
                select count(*)
                  from information_schema.columns
                 where table_schema = 'artifact'
                   and table_name = 'specification_imported_artifacts'
                   and column_name in ('record_id','organization_id','domain_run_id','subject_digest',
                                       'context_snapshot_digest','policy_version','status',
                                       'independent_verifier_id','critical_open_risks','evidence_refs',
                                       'payload','external_operation_executed','human_approval_ref',
                                       'idempotency_key','observed_at','created_at')
                """).query(Integer.class).single(),
                "V44 specification records must survive the V77 namespace expansion");
        assertEquals(2, jdbc.sql("""
                select count(*)
                  from pg_policies
                 where schemaname = 'artifact'
                   and tablename in ('artifacts', 'specification_imported_artifacts')
                   and policyname in ('tenant_isolation', 'product_b37a_tenant_isolation')
                """).query(Integer.class).single(),
                "both the imported evidence relation and runtime artifact relation must remain tenant isolated");
        assertEquals(11, jdbc.sql("""
                select count(*)
                  from information_schema.columns
                 where table_schema = 'artifact'
                   and table_name = 'content_objects'
                   and column_name in ('id','tenant_id','content_sha256','byte_size','media_type',
                                       'backend_id','storage_key','object_state','quarantine_reason',
                                       'created_at','updated_at')
                """).query(Integer.class).single(),
                "V77 must own the canonical artifact.content_objects runtime shape");
        assertEquals(16, jdbc.sql("""
                select count(*)
                  from information_schema.columns
                 where table_schema = 'artifact'
                   and table_name = 'specification_imported_content_objects'
                   and column_name in ('record_id','organization_id','domain_run_id','subject_digest',
                                       'context_snapshot_digest','policy_version','status',
                                       'independent_verifier_id','critical_open_risks','evidence_refs',
                                       'payload','external_operation_executed','human_approval_ref',
                                       'idempotency_key','observed_at','created_at')
                """).query(Integer.class).single(),
                "V44 content-object evidence must survive the V77 namespace expansion");
        assertEquals(2, jdbc.sql("""
                select count(*)
                  from pg_policies
                 where schemaname = 'artifact'
                   and tablename in ('content_objects', 'specification_imported_content_objects')
                   and policyname in ('tenant_isolation', 'product_b37a_tenant_isolation')
                """).query(Integer.class).single(),
                "both content-object relations must remain tenant isolated");
        assertEquals(1417, jdbc.sql("select count(*) from pg_policies where policyname like 'product_b%_tenant_isolation'").query(Integer.class).single());

        // V55-V60 are a product loop, not only schema presence. Exercise the
        // security-definer API through the same JDBC shapes used at runtime.
        String ownerAccount = "acc-test-owner";
        String memberAccount = "acc-test-member";
        String organization = "org-test-hosted-loop";
        String ownerActor = "actor-test-owner";
        String memberActor = "actor-test-member";
        String ownerSubjectHash = "1".repeat(64);
        assertEquals(ownerAccount, jdbc.sql("""
                SELECT elmos_resolve_oidc_account(
                    :account, 'https://issuer.test', 'owner-subject',
                    'owner@example.test', true, 'Owner')
                """).param("account", ownerAccount).query(String.class).single());
        assertEquals(organization, jdbc.sql("""
                SELECT elmos_create_self_service_organization(
                    :account, :organization, 'Hosted Loop', :actor,
                    'cn-north', :subjectHash)
                """)
                .param("account", ownerAccount)
                .param("organization", organization)
                .param("actor", ownerActor)
                .param("subjectHash", ownerSubjectHash)
                .query(String.class).single());
        assertEquals("OWNER", jdbc.sql("""
                SELECT member_role FROM identity_membership_directory
                 WHERE account_id = :account AND organization_id = :organization
                """)
                .param("account", ownerAccount)
                .param("organization", organization)
                .query(String.class).single());

        String proofImage = "registry.example.test/elmos/modernization-proof-worker@sha256:"
                + "9".repeat(64);
        assertEquals(1, jdbc.sql("""
                INSERT INTO execution_jobs (
                    job_id, organization_id, actor_id, business_line, job_kind,
                    idempotency_key, request_digest, request_payload,
                    required_capability, runner_image)
                VALUES (
                    'job-v63-modernization-proof', :organization, :actor,
                    'MODERNIZATION_PROOF', 'batch105-108-proof-loop',
                    'idem-v63-modernization-proof', :digest, '{}'::jsonb,
                    'modernization:proof-loop', :image)
                RETURNING 1
                """)
                .param("organization", organization)
                .param("actor", ownerActor)
                .param("digest", "8".repeat(64))
                .param("image", proofImage)
                .query(Integer.class).single(),
                "the real V63 constraint must accept a digest-pinned modernization proof job");
        assertEquals("MODERNIZATION_PROOF", jdbc.sql("""
                SELECT business_line FROM execution_jobs
                 WHERE job_id = 'job-v63-modernization-proof'
                """).query(String.class).single());
        assertEquals(proofImage, jdbc.sql("""
                SELECT runner_image FROM execution_jobs
                 WHERE job_id = 'job-v63-modernization-proof'
                """).query(String.class).single());
        assertThrows(RuntimeException.class, () -> jdbc.sql("""
                INSERT INTO execution_jobs (
                    job_id, organization_id, actor_id, business_line, job_kind,
                    idempotency_key, request_digest, request_payload,
                    required_capability, runner_image)
                VALUES (
                    'job-v63-unknown-line', :organization, :actor,
                    'UNKNOWN_PROOF_LINE', 'must-fail', 'idem-v63-unknown-line',
                    :digest, '{}'::jsonb, 'modernization:proof-loop', :image)
                """)
                .param("organization", organization)
                .param("actor", ownerActor)
                .param("digest", "7".repeat(64))
                .param("image", proofImage)
                .update(),
                "V63 must continue to fail closed for unknown business lines");
        assertThrows(RuntimeException.class, () -> jdbc.sql("""
                INSERT INTO execution_jobs (
                    job_id, organization_id, actor_id, business_line, job_kind,
                    idempotency_key, request_digest, request_payload,
                    required_capability, runner_image)
                VALUES (
                    'job-v63-mutable-image', :organization, :actor,
                    'MODERNIZATION_PROOF', 'must-fail', 'idem-v63-mutable-image',
                    :digest, '{}'::jsonb, 'modernization:proof-loop',
                    'registry.example.test/elmos/modernization-proof-worker:latest')
                """)
                .param("organization", organization)
                .param("actor", ownerActor)
                .param("digest", "6".repeat(64))
                .update(),
                "a V63 modernization proof job must not weaken the immutable-image constraint");

        String firstRefresh = "a".repeat(64);
        String secondRefresh = "b".repeat(64);
        assertEquals("session-test-owner", jdbc.sql("""
                SELECT elmos_open_session(
                    'session-test-owner', :account, :organization, :token,
                    86400, 3600, ARRAY['OIDC'], 'browser', 'test', '127.0.0.0/24')
                """)
                .param("account", ownerAccount)
                .param("organization", organization)
                .param("token", firstRefresh)
                .query(String.class).single());
        assertEquals("ROTATED", jdbc.sql("""
                SELECT outcome FROM elmos_rotate_session_token(:current, :next, 3600)
                """)
                .param("current", firstRefresh)
                .param("next", secondRefresh)
                .query(String.class).single());
        assertEquals(organization, jdbc.sql("""
                SELECT organization_id FROM elmos_switch_session_organization(
                    'session-test-owner', :account, :organization)
                """)
                .param("account", ownerAccount)
                .param("organization", organization)
                .query(String.class).single());

        assertEquals(memberAccount, jdbc.sql("""
                SELECT elmos_resolve_oidc_account(
                    :account, 'https://issuer.test', 'member-subject',
                    'member@example.test', true, 'Member')
                """).param("account", memberAccount).query(String.class).single());
        String invitationTokenHash = "c".repeat(64);
        String destinationHmac = "d".repeat(64);
        assertEquals("invite-test-member", jdbc.sql("""
                SELECT elmos_create_organization_invitation(
                    'invite-test-member', :organization, :owner, :ownerActor,
                    :destination, 'm***@example.test', 'MEMBER', :token, 3600)
                """)
                .param("organization", organization)
                .param("owner", ownerAccount)
                .param("ownerActor", ownerActor)
                .param("destination", destinationHmac)
                .param("token", invitationTokenHash)
                .query(String.class).single());
        assertEquals(organization, jdbc.sql("""
                SELECT elmos_accept_organization_invitation(
                    :token, :destination, :account, :actor)
                """)
                .param("token", invitationTokenHash)
                .param("destination", destinationHmac)
                .param("account", memberAccount)
                .param("actor", memberActor)
                .query(String.class).single());
        assertEquals(2, jdbc.sql("""
                SELECT count(*) FROM elmos_list_organization_members(
                    :organization, :owner)
                """)
                .param("organization", organization)
                .param("owner", ownerAccount)
                .query(Integer.class).single());
        assertThrows(RuntimeException.class, () -> jdbc.sql("""
                SELECT elmos_update_organization_member(
                    :organization, :owner, :owner, 'VIEWER', false)
                """)
                .param("organization", organization)
                .param("owner", ownerAccount)
                .query(String.class).single(),
                "the database must protect the last active owner");

        var transactions = new org.springframework.transaction.support.TransactionTemplate(
                new org.springframework.jdbc.datasource.DataSourceTransactionManager(dataSource));
        var runnerStore = new JdbcRunnerRegistrationStore(jdbc, transactions);
        var enrollment = runnerStore.issueEnrollment(
                organization, "pool-test", ownerActor, 900);
        String firstNodeToken = "node-token-" + "e".repeat(40);
        String nextNodeToken = "node-token-" + "f".repeat(40);
        String firstNodeHash = sha256(firstNodeToken);
        String nextNodeHash = sha256(nextNodeToken);
        var nodeCredential = runnerStore.register(
                "runner-test-1", "pool-test", "0.1.0",
                java.util.List.of("generation:multi"), 2,
                enrollment.token(), firstNodeHash,
                true, true, true, true, "allow-test");
        assertEquals("runner-test-1", nodeCredential.runnerNodeId());
        var registeredFleet = runnerStore.listFleet(
                organization,
                io.elmos.workflow.RunnerRegistrationPort.FleetStatus.REGISTERED,
                10);
        assertEquals(1, registeredFleet.size());
        assertEquals("runner-test-1", registeredFleet.getFirst().runnerNodeId());
        assertEquals("pool-test", registeredFleet.getFirst().runnerPoolId());
        assertEquals(false, registeredFleet.getFirst().attestationVerified());
        assertEquals(0, runnerStore.listFleet(
                "org-other-tenant",
                io.elmos.workflow.RunnerRegistrationPort.FleetStatus.REGISTERED,
                10).size(),
                "the JDBC projection must bind RLS and must not enumerate another tenant's runners");
        assertThrows(
                io.elmos.workflow.RunnerRegistrationPort.RunnerAuthenticationException.class,
                () -> runnerStore.listFleet(organization, null, 102),
                "the persistence port must keep its own bounded-list invariant");
        runnerStore.verifyAttestation(
                organization, "runner-test-1", ownerActor);
        var readyFleet = runnerStore.listFleet(
                organization,
                io.elmos.workflow.RunnerRegistrationPort.FleetStatus.READY,
                10);
        assertEquals(1, readyFleet.size());
        assertTrue(readyFleet.getFirst().attestationVerified());
        var crossTenantAttestation = assertThrows(
                io.elmos.workflow.RunnerRegistrationPort.RunnerAuthenticationException.class,
                () -> runnerStore.verifyAttestation(
                        "org-other-tenant", "runner-test-1", ownerActor));
        var unknownAttestation = assertThrows(
                io.elmos.workflow.RunnerRegistrationPort.RunnerAuthenticationException.class,
                () -> runnerStore.verifyAttestation(
                        "org-other-tenant", "runner-missing", ownerActor));
        assertEquals("ELMOS_RUNNER_UNKNOWN", crossTenantAttestation.code());
        assertEquals(crossTenantAttestation.code(), unknownAttestation.code(),
                "cross-tenant and nonexistent attestation targets must not be enumerable");
        var crossTenantDrain = assertThrows(
                io.elmos.workflow.RunnerRegistrationPort.RunnerAuthenticationException.class,
                () -> runnerStore.requestDrain(
                        "org-other-tenant", "runner-test-1", ownerActor));
        var unknownDrain = assertThrows(
                io.elmos.workflow.RunnerRegistrationPort.RunnerAuthenticationException.class,
                () -> runnerStore.requestDrain(
                        "org-other-tenant", "runner-missing", ownerActor));
        assertEquals("ELMOS_RUNNER_UNKNOWN", crossTenantDrain.code());
        assertEquals(crossTenantDrain.code(), unknownDrain.code(),
                "cross-tenant and nonexistent drain targets must not be enumerable");
        runnerStore.requestDrain(organization, "runner-test-1", ownerActor);
        assertEquals(1, runnerStore.listFleet(
                organization,
                io.elmos.workflow.RunnerRegistrationPort.FleetStatus.DRAINING,
                10).size());
        runnerStore.authorizeNode("runner-test-1", firstNodeToken);
        assertEquals(
                "runner-test-1",
                runnerStore.resume(
                        "runner-test-1",
                        firstNodeToken).runnerNodeId());
        runnerStore.rotateNodeCredential(
                "runner-test-1", firstNodeToken, nextNodeHash,
                "rotate-test-request-1");
        // Same request is replay-safe after an unknown response.
        runnerStore.rotateNodeCredential(
                "runner-test-1", firstNodeToken, nextNodeHash,
                "rotate-test-request-1");
        runnerStore.authorizeNode("runner-test-1", nextNodeToken);
        assertEquals(
                "runner-test-1",
                runnerStore.resume(
                        "runner-test-1",
                        nextNodeToken).runnerNodeId());
        assertThrows(
                io.elmos.workflow.RunnerRegistrationPort.RunnerAuthenticationException.class,
                () -> runnerStore.authorizeNode("runner-test-1", firstNodeToken));
    }

    private static void verifyPlatformAdminIdentityBoundary(
            org.springframework.jdbc.core.simple.JdbcClient jdbc) {
        jdbc.sql("""
                INSERT INTO accounts (
                    account_id, display_name, primary_email,
                    email_verified_at, phone_verified_at, status)
                VALUES
                    ('acct-platform-target', 'Designated administrator',
                     'ZPCHONEY@GMAIL.COM', now(), NULL, 'ACTIVE'),
                    ('acct-platform-other', 'Other verified user',
                     'other-platform@example.test', now(), NULL, 'ACTIVE'),
                    ('acct-platform-alias', 'Alias user',
                     'zpchoney+alias@gmail.com', now(), NULL, 'ACTIVE'),
                    ('acct-platform-whitespace', 'Non-canonical user',
                     ' zpchoney@gmail.com ', now(), NULL, 'ACTIVE')
                """).update();

        assertEquals("DENIED_POLICY", jdbc.sql("""
                SELECT elmos_platform_bootstrap_admin(
                    'acct-platform-other', 'negative database identity test')
                """).query(String.class).single());
        assertEquals("DENIED_POLICY", jdbc.sql("""
                SELECT elmos_platform_bootstrap_admin(
                    'acct-platform-alias', 'alias must not authorize')
                """).query(String.class).single());
        assertEquals("DENIED_POLICY", jdbc.sql("""
                SELECT elmos_platform_bootstrap_admin(
                    'acct-platform-whitespace', 'non-canonical value must not authorize')
                """).query(String.class).single());

        assertEquals("ALLOWED", jdbc.sql("""
                SELECT elmos_platform_bootstrap_admin(
                    'acct-platform-target', 'verified designated administrator test')
                """).query(String.class).single());
        assertEquals("ALLOWED", jdbc.sql("""
                SELECT elmos_platform_authorize(
                    'acct-platform-target', 'PLATFORM_VIEWER',
                    'V79_LIVE_BOUNDARY_TEST', NULL, NULL)
                """).query(String.class).single());
        assertEquals("DENIED_POLICY", jdbc.sql("""
                SELECT elmos_platform_grant_admin(
                    'acct-platform-target', 'acct-platform-other',
                    'PLATFORM_VIEWER', 'must remain the only administrator')
                """).query(String.class).single());

        assertThrows(RuntimeException.class, () -> jdbc.sql("""
                INSERT INTO platform_administrators (
                    account_id, platform_role, grant_reason)
                VALUES (
                    'acct-platform-alias', 'PLATFORM_VIEWER',
                    'attempt to bypass the grant function')
                """).update(), "the table trigger must block a direct grant bypass");

        // Revoking email verification is a safety operation and must succeed.
        // A verified phone keeps the ACTIVE account shape valid while V79
        // automatically revokes the administrator record in the same statement.
        assertEquals(1, jdbc.sql("""
                UPDATE accounts
                   SET email_verified_at = NULL, phone_verified_at = now()
                 WHERE account_id = 'acct-platform-target'
                """).update());
        assertEquals(0, jdbc.sql("""
                SELECT count(*) FROM platform_administrators
                 WHERE account_id = 'acct-platform-target' AND revoked_at IS NULL
                """).query(Integer.class).single());
        assertEquals(1, jdbc.sql("""
                SELECT count(*) FROM platform_admin_access_log
                 WHERE admin_account_id = 'acct-platform-target'
                   AND operation = 'AUTO_REVOKE_IDENTITY'
                """).query(Integer.class).single());
        assertEquals("DENIED_NOT_ADMIN", jdbc.sql("""
                SELECT elmos_platform_authorize(
                    'acct-platform-target', 'PLATFORM_VIEWER',
                    'V79_REVOKED_BOUNDARY_TEST', NULL, NULL)
                """).query(String.class).single());

        // Restoring the verified email does not silently restore privilege;
        // the direct-operator bootstrap remains an explicit audited action.
        assertEquals(1, jdbc.sql("""
                UPDATE accounts SET email_verified_at = now()
                 WHERE account_id = 'acct-platform-target'
                """).update());
        assertEquals("DENIED_NOT_ADMIN", jdbc.sql("""
                SELECT elmos_platform_authorize(
                    'acct-platform-target', 'PLATFORM_VIEWER',
                    'V79_NOT_AUTO_REGRANTED_TEST', NULL, NULL)
                """).query(String.class).single());
        assertEquals("ALLOWED", jdbc.sql("""
                SELECT elmos_platform_bootstrap_admin(
                    'acct-platform-target', 'explicitly restore after re-verification')
                """).query(String.class).single());
    }

    private static void verifyPlatformAdminConcurrentWriteOrder(
            DataSource dataSource,
            org.springframework.jdbc.core.simple.JdbcClient jdbc) {
        var executor = Executors.newFixedThreadPool(2);
        jdbc.sql("""
                CREATE FUNCTION elmos_test_pause_platform_admin_identity_loss()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    PERFORM pg_catalog.pg_advisory_xact_lock(1162628425, 7901);
                    RETURN NEW;
                END;
                $$
                """).update();
        jdbc.sql("""
                CREATE TRIGGER "00_test_pause_platform_admin_identity_loss"
                AFTER UPDATE OF primary_email, email_verified_at, status ON accounts
                FOR EACH ROW EXECUTE FUNCTION elmos_test_pause_platform_admin_identity_loss()
                """).update();
        try (Connection barrier = dataSource.getConnection();
             Connection administrator = dataSource.getConnection();
             Connection account = dataSource.getConnection()) {
            barrier.setAutoCommit(false);
            administrator.setAutoCommit(false);
            account.setAutoCommit(false);
            setPlatformAdminConcurrencyTimeouts(administrator);
            setPlatformAdminConcurrencyTimeouts(account);
            int accountPid = backendPid(account);
            int administratorPid = backendPid(administrator);

            // Hold a test-only barrier. The account UPDATE first acquires the
            // production identity mutex and its account row, then pauses in the
            // alphabetically earlier AFTER trigger. A concurrent direct admin
            // UPDATE must wait on the production advisory mutex before it can
            // acquire the administrator row. Without the production statement
            // triggers this exact interleaving forms account-row <-> admin-row
            // and PostgreSQL reports SQLSTATE 40P01 when the pause is released.
            barrier.createStatement().execute(
                    "SELECT pg_advisory_xact_lock(1162628425, 7901)");
            var accountUpdate = executor.submit(() -> {
                int changed = account.createStatement().executeUpdate("""
                        UPDATE accounts
                           SET email_verified_at = NULL, phone_verified_at = now()
                         WHERE account_id = 'acct-platform-target'
                        """);
                account.commit();
                return changed;
            });
            assertTrue(waitingOnPlatformAdminAdvisoryLock(jdbc, accountPid),
                    "the account transaction must reach the controlled AFTER-trigger barrier");
            var administratorUpdate = executor.submit(() -> {
                int changed = administrator.createStatement().executeUpdate("""
                        UPDATE platform_administrators
                           SET revoked_at = revoked_at
                         WHERE account_id = 'acct-platform-target'
                        """);
                administrator.commit();
                return changed;
            });
            assertTrue(waitingOnPlatformAdminAdvisoryLock(jdbc, administratorPid),
                    "the admin statement must wait on the production mutex before its row lock");
            barrier.commit();
            assertEquals(1, accountUpdate.get(10, TimeUnit.SECONDS));
            assertEquals(1, administratorUpdate.get(10, TimeUnit.SECONDS));
            assertEquals(0, jdbc.sql("""
                    SELECT count(*) FROM platform_administrators
                     WHERE account_id = 'acct-platform-target' AND revoked_at IS NULL
                    """).query(Integer.class).single(),
                    "the serialized account write must still auto-revoke");

            assertEquals(1, jdbc.sql("""
                    UPDATE accounts SET email_verified_at = now()
                     WHERE account_id = 'acct-platform-target'
                    """).update());
            assertEquals("ALLOWED", jdbc.sql("""
                    SELECT elmos_platform_bootstrap_admin(
                        'acct-platform-target', 'restore for concurrent upsert test')
                    """).query(String.class).single());

            // Exercise the inverse direction and the real ON CONFLICT UPDATE
            // shape used by grant/bootstrap. The upsert waits before taking its
            // row while the account statement owns the same transaction mutex.
            assertEquals(1, account.createStatement().executeUpdate("""
                    UPDATE accounts
                       SET primary_email = primary_email
                     WHERE account_id = 'acct-platform-target'
                    """));
            var administratorUpsert = executor.submit(
                    () -> {
                        int changed = administrator.createStatement().executeUpdate("""
                                INSERT INTO platform_administrators (
                                    account_id, platform_role, grant_reason)
                                VALUES (
                                    'acct-platform-target', 'PLATFORM_APPROVER',
                                    'concurrent lock-order upsert test')
                                ON CONFLICT (account_id) DO UPDATE
                                    SET platform_role = EXCLUDED.platform_role,
                                        revoked_at = NULL,
                                        revoked_by = NULL,
                                        revoke_reason = NULL,
                                        state_version = platform_administrators.state_version + 1
                                """);
                        administrator.commit();
                        return changed;
                    });
            assertTrue(waitingOnPlatformAdminAdvisoryLock(jdbc, administratorPid),
                    "the administrator upsert must wait before acquiring its row lock");
            account.commit();
            assertEquals(1, administratorUpsert.get(10, TimeUnit.SECONDS));
            assertEquals(1, jdbc.sql("""
                    SELECT count(*) FROM platform_administrators
                     WHERE account_id = 'acct-platform-target' AND revoked_at IS NULL
                    """).query(Integer.class).single());
        } catch (Exception error) {
            throw new AssertionError(
                    "PostgreSQL 17 concurrent platform-admin writes must complete without 40P01",
                    error);
        } finally {
            executor.shutdownNow();
            jdbc.sql("DROP TRIGGER IF EXISTS \"00_test_pause_platform_admin_identity_loss\" ON accounts")
                    .update();
            jdbc.sql("DROP FUNCTION IF EXISTS elmos_test_pause_platform_admin_identity_loss()")
                    .update();
        }
    }

    private static void setPlatformAdminConcurrencyTimeouts(Connection connection)
            throws Exception {
        try (var statement = connection.createStatement()) {
            statement.execute("SET statement_timeout = '10s'");
            statement.execute("SET lock_timeout = '8s'");
            statement.execute("SET deadlock_timeout = '100ms'");
        }
    }

    private static void verifyRuntimeRoleUsesFunctionsButCannotBypassPlatformAdminBoundary(
            DataSource dataSource,
            org.springframework.jdbc.core.simple.JdbcClient jdbc) {
        String role = "elmos_control_plane_runtime_acl_test";
        String[] functionSignatures = {
                "elmos_platform_resolve_admin_account(varchar,varchar)",
                "elmos_platform_wallet_overview(varchar,varchar,integer)",
                "elmos_platform_wallet_ledger(varchar,varchar,integer,integer)",
                "elmos_platform_topup_orders(varchar,varchar,integer)",
                "elmos_platform_job_overview(varchar,varchar,varchar,integer)",
                "elmos_platform_wallet_adjust(varchar,varchar,varchar,numeric,varchar,varchar)",
                "elmos_platform_grant_admin(varchar,varchar,varchar,varchar)",
                "elmos_platform_revoke_admin(varchar,varchar,varchar)",
                "elmos_platform_authorize(varchar,varchar,varchar,varchar,varchar)"};
        jdbc.sql("CREATE ROLE " + role + " LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS "
                + "NOCREATEDB NOCREATEROLE NOREPLICATION").update();
        jdbc.sql("GRANT USAGE ON SCHEMA public TO " + role).update();
        for (String signature : functionSignatures) {
            jdbc.sql("GRANT EXECUTE ON FUNCTION " + signature + " TO " + role).update();
        }
        try {
            assertEquals(0, jdbc.sql("""
                    SELECT count(*) FROM pg_auth_members
                     WHERE member = (SELECT oid FROM pg_roles WHERE rolname = :role)
                    """).param("role", role).query(Integer.class).single());
            for (String signature : functionSignatures) {
                assertEquals(true, jdbc.sql("""
                        SELECT has_function_privilege(:role, :signature, 'EXECUTE')
                        """)
                        .param("role", role)
                        .param("signature", signature)
                        .query(Boolean.class).single(),
                        () -> "runtime role lacks allowlisted function: " + signature);
            }
            assertEquals(false, jdbc.sql("""
                    SELECT has_function_privilege(
                        :role,
                        'elmos_platform_bootstrap_admin(varchar,varchar)',
                        'EXECUTE')
                    """).param("role", role).query(Boolean.class).single(),
                    "the application login must never receive the operator bootstrap path");
            assertEquals(0, jdbc.sql("""
                    SELECT count(*)
                      FROM (VALUES
                        (has_table_privilege(:role, 'accounts', 'SELECT')),
                        (has_table_privilege(:role, 'accounts', 'INSERT')),
                        (has_table_privilege(:role, 'accounts', 'UPDATE')),
                        (has_table_privilege(:role, 'accounts', 'DELETE')),
                        (has_table_privilege(:role, 'accounts', 'TRUNCATE')),
                        (has_table_privilege(:role, 'platform_administrators', 'SELECT')),
                        (has_table_privilege(:role, 'platform_administrators', 'INSERT')),
                        (has_table_privilege(:role, 'platform_administrators', 'UPDATE')),
                        (has_table_privilege(:role, 'platform_administrators', 'DELETE')),
                        (has_table_privilege(:role, 'platform_administrators', 'TRUNCATE'))
                      ) privilege(allowed)
                     WHERE allowed
                    """).param("role", role).query(Integer.class).single(),
                    "an ungranted runtime role must have no direct identity-table privilege");
            try (Connection connection = dataSource.getConnection();
                 var statement = connection.createStatement()) {
                statement.execute("SET ROLE " + role);
                for (String sql : new String[]{
                        "SELECT elmos_platform_resolve_admin_account('missing-org','missing-actor')",
                        "SELECT count(*) FROM elmos_platform_wallet_overview('acct-platform-other',NULL,1)",
                        "SELECT count(*) FROM elmos_platform_wallet_ledger('acct-platform-other','missing-org',1,0)",
                        "SELECT count(*) FROM elmos_platform_topup_orders('acct-platform-other',NULL,1)",
                        "SELECT count(*) FROM elmos_platform_job_overview('acct-platform-other',NULL,NULL,1)",
                        "SELECT count(*) FROM elmos_platform_wallet_adjust('acct-platform-other','missing-org','CREDIT',1,'denied','acl-test')",
                        "SELECT elmos_platform_grant_admin('acct-platform-other','acct-platform-target','PLATFORM_VIEWER','denied')",
                        "SELECT elmos_platform_revoke_admin('acct-platform-other','acct-platform-target','denied')",
                        "SELECT elmos_platform_authorize('acct-platform-other','PLATFORM_VIEWER','V79_RUNTIME_ROLE_ACL_TEST',NULL,NULL)"}) {
                    assertTrue(statement.execute(sql),
                            () -> "runtime role could not execute allowlisted function: " + sql);
                }
                for (String sql : new String[]{
                        "SELECT account_id FROM accounts LIMIT 1",
                        "UPDATE accounts SET status = status WHERE false",
                        "INSERT INTO platform_administrators "
                                + "(account_id, platform_role, grant_reason) "
                                + "VALUES ('denied', 'PLATFORM_VIEWER', 'denied')",
                        "DELETE FROM platform_administrators WHERE false",
                        "TRUNCATE TABLE platform_administrators"}) {
                    SQLException denied = assertThrows(
                            SQLException.class,
                            () -> statement.execute(sql),
                            () -> "runtime role unexpectedly executed: " + sql);
                    assertEquals("42501", denied.getSQLState(),
                            "the refusal must be PostgreSQL insufficient_privilege");
                }
                statement.execute("RESET ROLE");
            }
        } catch (SQLException error) {
            throw new AssertionError("runtime role ACL negative test failed", error);
        } finally {
            jdbc.sql("DROP OWNED BY " + role).update();
            jdbc.sql("DROP ROLE IF EXISTS " + role).update();
        }
    }

    private static int backendPid(Connection connection) throws Exception {
        try (var statement = connection.createStatement();
             var result = statement.executeQuery("SELECT pg_backend_pid()")) {
            assertTrue(result.next());
            return result.getInt(1);
        }
    }

    private static boolean waitingOnPlatformAdminAdvisoryLock(
            org.springframework.jdbc.core.simple.JdbcClient jdbc,
            int backendPid) throws InterruptedException {
        for (int attempt = 0; attempt < 200; attempt++) {
            int waiting = jdbc.sql("""
                    SELECT count(*) FROM pg_stat_activity
                     WHERE pid = :pid
                       AND wait_event_type = 'Lock'
                       AND wait_event = 'advisory'
                    """).param("pid", backendPid).query(Integer.class).single();
            if (waiting == 1) {
                return true;
            }
            LockSupport.parkNanos(TimeUnit.MILLISECONDS.toNanos(25));
        }
        return false;
    }

    private static String sha256(String value) {
        try {
            return java.util.HexFormat.of().formatHex(
                    java.security.MessageDigest.getInstance("SHA-256")
                            .digest(value.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }
}
