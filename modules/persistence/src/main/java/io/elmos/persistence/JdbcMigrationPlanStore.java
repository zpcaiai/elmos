package io.elmos.persistence;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.planning.MigrationPlanStore;
import io.elmos.planning.PlanningModels;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import java.util.Map;

@Repository
public final class JdbcMigrationPlanStore implements MigrationPlanStore {
    private final JdbcClient jdbc; private final ObjectMapper json;
    public JdbcMigrationPlanStore(JdbcClient jdbc, ObjectMapper json) { this.jdbc = jdbc; this.json = json; }

    @Override @Transactional public void save(PlanningModels.MigrationPlan plan, SaveContext context) {
        validate(plan, context);
        var existing = jdbc.sql("select plan_sha256 from migration_plan_revisions where migration_plan_id=:id and plan_version=:version")
                .param("id",plan.planId()).param("version",context.planVersion()).query(String.class).optional();
        if (existing.isPresent()) { if (!existing.get().equals(context.planSha256())) throw new SecurityException("immutable migration plan collision"); return; }
        jdbc.sql("insert into migration_plans(migration_plan_id,organization_id,snapshot_id,plan_version,status,source_profile,target_profile) values(:id,:org,:snapshot,:version,:status,:source,:target) on conflict do nothing")
                .param("id",plan.planId()).param("org",context.organizationId()).param("snapshot",plan.snapshotId()).param("version",context.planVersion())
                .param("status",plan.status().name()).param("source",toJson(Map.of("healthReportId",plan.healthReportId())))
                .param("target",toJson(plan.target())).update();
        jdbc.sql("insert into migration_plan_revisions(migration_plan_id,plan_version,health_report_id,compatibility_matrix_version,status,plan_artifact_ref,plan_sha256,generated_at) values(:id,:version,:health,:matrix,:status,:artifact,:sha,current_timestamp)")
                .param("id",plan.planId()).param("version",context.planVersion()).param("health",plan.healthReportId()).param("matrix",context.compatibilityMatrixVersion())
                .param("status",plan.status().name()).param("artifact",context.planArtifactRef()).param("sha",context.planSha256()).update();
        jdbc.sql("insert into migration_target_profiles(migration_plan_id,plan_version,java_version,spring_boot_line,jakarta_namespace,build_tool_strategy,evidence_status,assumptions) values(:id,:version,:java,:boot,:jakarta,:build,:status,cast(:assumptions as jsonb))")
                .param("id",plan.planId()).param("version",context.planVersion()).param("java",plan.target().javaVersion()).param("boot",plan.target().springBootLine())
                .param("jakarta",plan.target().jakartaNamespace()).param("build",plan.target().buildToolStrategy()).param("status",plan.target().status().name()).param("assumptions",toJson(plan.target().assumptions())).update();
        int index = 0;
        for (PlanningModels.CompatibilityDecision decision : plan.compatibility()) jdbc.sql("insert into compatibility_decisions(compatibility_decision_id,migration_plan_id,plan_version,component,source_version,target_version,compatible,migration_required,evidence_status,rationale,matrix_version) values(:decision,:id,:version,:component,:source,:target,:compatible,:migration,:status,:rationale,:matrix)")
                .param("decision","compat-"+(++index)+"-"+plan.planId().substring(Math.max(0,plan.planId().length()-20))).param("id",plan.planId()).param("version",context.planVersion())
                .param("component",decision.component()).param("source",decision.sourceVersion()).param("target",decision.targetVersion()).param("compatible",decision.compatible())
                .param("migration",decision.migrationRequired()).param("status",decision.status().name()).param("rationale",decision.rationale()).param("matrix",decision.matrixVersion()).update();
        for (PlanningModels.MigrationStep step : plan.steps()) jdbc.sql("insert into migration_plan_steps(migration_plan_id,plan_version,step_id,step_type,objective,risk,automation_score,approval_required,required_evidence) values(:id,:version,:step,:type,:objective,:risk,:automation,:approval,cast(:evidence as jsonb))")
                .param("id",plan.planId()).param("version",context.planVersion()).param("step",step.stepId()).param("type",step.type().name()).param("objective",step.objective())
                .param("risk",step.risk().name()).param("automation",step.automationScore()).param("approval",step.approvalRequired()).param("evidence",toJson(step.requiredEvidence())).update();
        for (PlanningModels.MigrationStep step : plan.steps()) for (String parent : step.dependsOn()) jdbc.sql("insert into migration_step_dependencies(migration_plan_id,plan_version,step_id,depends_on_step_id) values(:id,:version,:step,:parent)")
                .param("id",plan.planId()).param("version",context.planVersion()).param("step",step.stepId()).param("parent",parent).update();
        score(plan, context, "MIGRATION_RISK", plan.migrationRisk()); score(plan, context, "AUTOMATION", plan.automation());
        effort(plan.planId(),context.planVersion(),"TOTAL",null,plan.totalEffort());
        for (PlanningModels.MigrationStep step : plan.steps()) effort(plan.planId(),context.planVersion(),"STEP-"+step.stepId(),step.stepId(),step.effort());
        for (PlanningModels.MigrationWave wave : plan.waves()) {
            jdbc.sql("insert into migration_waves(migration_plan_id,plan_version,wave_number,exit_criterion) values(:id,:version,:wave,:criterion)")
                    .param("id",plan.planId()).param("version",context.planVersion()).param("wave",wave.number()).param("criterion",wave.exitCriterion()).update();
            for (String step : wave.stepIds()) jdbc.sql("insert into migration_wave_steps(migration_plan_id,plan_version,wave_number,step_id) values(:id,:version,:wave,:step)")
                    .param("id",plan.planId()).param("version",context.planVersion()).param("wave",wave.number()).param("step",step).update();
        }
        for (PlanningModels.ApprovalGate gate : plan.approvalGates()) jdbc.sql("insert into migration_approval_gates(approval_gate_id,migration_plan_id,plan_version,gate_type,before_step_id,reason,required_evidence,blocking) values(:gate,:id,:version,:type,:step,:reason,cast(:evidence as jsonb),:blocking)")
                .param("gate",gate.gateId()).param("id",plan.planId()).param("version",context.planVersion()).param("type",gate.type().name()).param("step",gate.beforeStepId())
                .param("reason",gate.reason()).param("evidence",toJson(gate.requiredEvidence())).param("blocking",gate.blocking()).update();
    }
    private void score(PlanningModels.MigrationPlan plan, SaveContext context, String type, PlanningModels.ScoreBreakdown score) {
        jdbc.sql("insert into migration_risk_scores(migration_plan_id,plan_version,score_type,score,factors,rationale) values(:id,:version,:type,:score,cast(:factors as jsonb),cast(:rationale as jsonb))")
                .param("id",plan.planId()).param("version",context.planVersion()).param("type",type).param("score",score.score()).param("factors",toJson(score.factors())).param("rationale",toJson(score.rationale())).update();
    }
    private void effort(String planId,int version,String key,String step,PlanningModels.EffortRange effort) {
        jdbc.sql("insert into migration_effort_estimates(migration_plan_id,plan_version,step_id,minimum_person_days,likely_person_days,maximum_person_days,confidence,assumptions,estimate_key) values(:id,:version,:step,:minimum,:likely,:maximum,:confidence,cast(:assumptions as jsonb),:key)")
                .param("id",planId).param("version",version).param("step",step).param("minimum",effort.minimumPersonDays()).param("likely",effort.likelyPersonDays())
                .param("maximum",effort.maximumPersonDays()).param("confidence",effort.confidence()).param("assumptions",toJson(effort.assumptions())).param("key",key).update();
    }
    private static void validate(PlanningModels.MigrationPlan plan, SaveContext context) {
        if (plan == null || context == null || context.organizationId() == null || context.organizationId().isBlank() || context.planVersion() < 1
                || context.compatibilityMatrixVersion() == null || context.compatibilityMatrixVersion().isBlank() || context.planArtifactRef() == null || context.planArtifactRef().isBlank()
                || context.planSha256() == null || !context.planSha256().matches("[0-9a-f]{64}")) throw new IllegalArgumentException("migration plan persistence context is invalid");
    }
    private String toJson(Object value) { try { return json.writeValueAsString(value); } catch (JsonProcessingException error) { throw new IllegalArgumentException("plan metadata is not serializable",error); } }
}
