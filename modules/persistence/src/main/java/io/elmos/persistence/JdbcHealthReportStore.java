package io.elmos.persistence;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.health.HealthModels;
import io.elmos.health.HealthReportStore;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Objects;

@Repository
public final class JdbcHealthReportStore implements HealthReportStore {
    private final JdbcClient jdbc; private final ObjectMapper json;
    public JdbcHealthReportStore(JdbcClient jdbc, ObjectMapper json) { this.jdbc = jdbc; this.json = json; }

    @Override @Transactional public void save(HealthModels.LegacyHealthReport report, SaveContext context) {
        Objects.requireNonNull(report); validate(context);
        var existing = jdbc.sql("select report_sha256 from health_reports where health_report_id=:id").param("id", report.reportId()).query(String.class).optional();
        if (existing.isPresent()) { if (!existing.get().equals(context.reportSha256())) throw new SecurityException("immutable health report collision"); return; }
        String runId = id("health-run", report.reportId());
        jdbc.sql("insert into health_check_runs(health_check_run_id,organization_id,snapshot_id,scanner_version,policy_hash,status,started_at,finished_at,correlation_id) values(:id,:org,:snapshot,:scanner,:policy,:status,:at,:at,:correlation)")
                .param("id",runId).param("org",context.organizationId()).param("snapshot",report.snapshotId()).param("scanner",context.scannerVersion())
                .param("policy",context.policyHash()).param("status",report.status().name()).param("at",report.generatedAt()).param("correlation",context.correlationId()).update();
        int index = 0;
        for (HealthModels.Module module : report.modules()) jdbc.sql("insert into health_project_modules(health_module_id,health_check_run_id,module_path,coordinates,build_system,descriptor_hash) values(:id,:run,:path,:coordinates,:build,:hash)")
                .param("id",id("module",runId+":"+(index++))).param("run",runId).param("path",module.path()).param("coordinates",module.coordinate())
                .param("build",module.buildSystem().name()).param("hash",sha(module.coordinate()+"\0"+module.path())).update();
        index = 0;
        for (HealthModels.Dependency dependency : report.dependencies()) jdbc.sql("insert into health_dependencies(health_dependency_id,health_check_run_id,module_path,group_id,artifact_id,version,scope,direct,resolution_status) values(:id,:run,:module,:group,:artifact,:version,:scope,:direct,:status)")
                .param("id",id("dependency",runId+":"+(index++))).param("run",runId).param("module",dependency.modulePath()).param("group",dependency.groupId())
                .param("artifact",dependency.artifactId()).param("version",dependency.version()).param("scope",dependency.scope()).param("direct",dependency.direct())
                .param("status",dependency.resolved()?"RESOLVED":"INCONCLUSIVE").update();
        index = 0;
        for (HealthModels.Vulnerability vulnerability : report.vulnerabilities()) jdbc.sql("insert into health_vulnerabilities(health_vulnerability_id,health_check_run_id,advisory_id,dependency_coordinates,severity,fixed_version,advisory_url,observed_at,provider) values(:id,:run,:advisory,:dependency,:severity,:fixed,:url,:observed,:provider)")
                .param("id",id("vulnerability",runId+":"+(index++))).param("run",runId).param("advisory",vulnerability.id()).param("dependency",vulnerability.dependency())
                .param("severity",vulnerability.severity().name()).param("fixed",vulnerability.fixedVersion()).param("url",vulnerability.advisoryUrl())
                .param("observed",vulnerability.observedAt()).param("provider",report.vulnerabilityEvidence().provider()).update();
        index = 0;
        for (HealthModels.Finding finding : report.findings()) jdbc.sql("insert into health_findings(health_finding_id,health_check_run_id,finding_code,category,severity,evidence_status,location,message,attributes) values(:id,:run,:code,:category,:severity,:status,:location,:message,cast(:attributes as jsonb))")
                .param("id",id("finding",runId+":"+(index++))).param("run",runId).param("code",finding.code()).param("category",finding.category())
                .param("severity",finding.severity().name()).param("status",finding.status().name()).param("location",finding.location()).param("message",finding.message()).param("attributes",toJson(finding.attributes())).update();
        index = 0;
        for (HealthModels.PublicApi api : report.publicApis()) jdbc.sql("insert into health_public_apis(health_public_api_id,health_check_run_id,api_kind,owner,signature,location) values(:id,:run,:kind,:owner,:signature,:location)")
                .param("id",id("api",runId+":"+(index++))).param("run",runId).param("kind",api.kind()).param("owner",api.owner()).param("signature",api.signature()).param("location",api.location()).update();
        HealthModels.TestReadiness test = report.testReadiness();
        jdbc.sql("insert into health_test_readiness(health_check_run_id,production_files,test_files,junit_detected,integration_tests_detected,coverage_plugin_detected,test_to_production_ratio,evidence_status) values(:run,:production,:tests,:junit,:integration,:coverage,:ratio,:status)")
                .param("run",runId).param("production",test.productionFiles()).param("tests",test.testFiles()).param("junit",test.junitDetected())
                .param("integration",test.integrationTestsDetected()).param("coverage",test.coveragePluginDetected()).param("ratio",test.testToProductionRatio()).param("status",test.status().name()).update();
        jdbc.sql("insert into health_reports(health_report_id,health_check_run_id,snapshot_id,health_score,overall_risk,evidence_status,report_artifact_ref,report_sha256,generated_at) values(:id,:run,:snapshot,:score,:risk,:status,:artifact,:sha,:at)")
                .param("id",report.reportId()).param("run",runId).param("snapshot",report.snapshotId()).param("score",report.healthScore()).param("risk",report.overallRisk().name())
                .param("status",report.status().name()).param("artifact",context.reportArtifactRef()).param("sha",context.reportSha256()).param("at",report.generatedAt()).update();
    }
    private static void validate(SaveContext context) { if (context == null || blank(context.organizationId()) || blank(context.correlationId()) || blank(context.scannerVersion())
            || context.policyHash() == null || !context.policyHash().matches("[0-9a-f]{64,80}") || blank(context.reportArtifactRef())
            || context.reportSha256() == null || !context.reportSha256().matches("[0-9a-f]{64}")) throw new IllegalArgumentException("health report persistence context is invalid"); }
    private String toJson(Object value) { try { return json.writeValueAsString(value); } catch (JsonProcessingException error) { throw new IllegalArgumentException("health metadata is not serializable", error); } }
    private static String id(String prefix,String value) { return prefix+"-"+sha(value).substring(0, Math.min(48,64-prefix.length())); }
    private static String sha(String value) { try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); } catch (Exception error) { throw new IllegalStateException(error); } }
    private static boolean blank(String value) { return value == null || value.isBlank(); }
}
