package io.elmos.persistence;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers(disabledWithoutDocker = true)
class FlywayMigrationTest {
    @Container static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:17.5-alpine");
    @Test void createsAllAuthoritativeSchemasThroughProductBatchThirtyEightAndMigrationPackAdmission() {
        var flyway=Flyway.configure().dataSource(POSTGRES.getJdbcUrl(),POSTGRES.getUsername(),POSTGRES.getPassword()).load();
        assertEquals(47,flyway.migrate().migrationsExecuted);
        var jdbc=org.springframework.jdbc.core.simple.JdbcClient.create(new org.springframework.jdbc.datasource.DriverManagerDataSource(POSTGRES.getJdbcUrl(),POSTGRES.getUsername(),POSTGRES.getPassword()));
        assertTrue(jdbc.sql("select count(*) from information_schema.tables where table_schema='public'").query(Integer.class).single() >= 1240);
        assertEquals(56, jdbc.sql("select count(*) from information_schema.tables where table_schema='public' and table_name in ('recipe_execution_manifests','repair_tasks','validation_decisions','delivery_snapshots','organizations','authorization_decisions','runner_job_leases','audit_events','entitlements','orders','project_status_snapshots','support_tickets','dotnet_solutions','msbuild_evaluations','dotnet_fingerprints','roslyn_symbols','dotnet_migration_plans','aspnet_inventories','wcf_services','ef_contexts','dotnet_compatibility_results','python_projects','python_environment_snapshots','python_symbols','python_migration_plans','django_applications','data_pipelines','ml_model_artifacts','system_landscapes','system_dependency_edges','api_contracts','message_contracts','contract_consumer_matrix','composite_migration_plans','compatibility_windows','data_ownership_records','shadow_experiments','traffic_shift_plans','system_cutover_plans','decommission_plans','client_applications','frontend_workspaces','frontend_routes','visual_baselines','accessibility_findings','client_release_plans','database_estates','database_objects','sql_workloads','schema_conversions','bulk_load_runs','data_quality_results','lakehouse_tables','semantic_metrics','lineage_events','governance_policies')").query(Integer.class).single());
        assertEquals(16, jdbc.sql("select count(*) from information_schema.tables where table_schema='public' and table_name in ('infrastructure_estates','physical_hosts','workloads','firewall_rules','storage_volumes','middleware_instances','workload_placement_decisions','container_images','kubernetes_clusters','serverless_functions','infrastructure_plans','observability_profiles','cost_allocations','chaos_experiments','portability_profiles','infrastructure_cutover_plans')").query(Integer.class).single());
        assertEquals(24, jdbc.sql("select count(*) from information_schema.tables where table_schema='public' and table_name in ('security_estates','security_assets','security_boundaries','security_identities','access_policies','cryptographic_assets','security_requirements','security_controls','control_assessments','software_components','sbom_documents','provenance_statements','vex_statements','security_tools','security_scans','security_findings','vulnerabilities','vulnerability_exposures','runtime_security_events','data_processing_activities','threat_models','compliance_catalogs','oscal_assessment_results','authorization_boundaries')").query(Integer.class).single());
        assertEquals(24, jdbc.sql("select count(*) from information_schema.tables where table_schema='public' and table_name in ('test_estates','test_framework_profiles','test_suites','test_cases','test_case_identities','test_executions','test_results','test_discovery_snapshots','quality_requirements','quality_risks','quality_coverage_records','test_portfolios','characterization_scenarios','golden_masters','contract_tests','provider_verifications','property_tests','mutation_runs','test_data_assets','test_environments','ai_test_candidates','flaky_test_profiles','quality_decisions','continuous_validation_runs')").query(Integer.class).single());
        assertTrue(jdbc.sql("select count(*) from pg_policies where schemaname='public' and policyname='tenant_isolation'").query(Integer.class).single() >= 1239);
        assertEquals(96, jdbc.sql("select count(*) from information_schema.tables where table_schema='public' and table_name like 'growth_%'").query(Integer.class).single());
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
        assertEquals(1416, jdbc.sql("select count(*) from information_schema.tables where table_schema in (" + productSchemas + ")").query(Integer.class).single());
        assertEquals(1417, jdbc.sql("select count(*) from pg_policies where policyname like 'product_b%_tenant_isolation'").query(Integer.class).single());
    }
}
