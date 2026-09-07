package io.elmos.companyseries;

import java.util.List;

import static io.elmos.companyseries.CompanySeriesModels.*;

/** Exact authoritative models, sequential gates, dimensions and reports for Batches 15-18. */
public final class CompanySeriesPrograms {
    private CompanySeriesPrograms() {}

    public static ProgramDefinition companyOperatingSystem() {
        return definition(15, "Company Operating and Governance System", "COGS",
                "company-operations-v1", "company-scale-operating-ready",
                gates("C15", "战略清晰", "执行系统一致", "组织与人才可承载", "财务和现金可控",
                        "融资和资本可治理", "治理、风险和董事会有效", "公司级规模化经营候选"),
                List.of("purpose-strategy", "strategic-execution", "organization-talent",
                        "financial-management", "capital-fundraising", "governance",
                        "enterprise-risk", "board-operations"),
                "company-operating-system",
                List.of("purpose", "strategy", "execution", "organization", "talent", "finance",
                        "capital", "governance", "risk", "board", "dashboards", "knowledge", "reports"),
                List.of("strategic-diagnosis-report.json", "annual-strategy-report.json",
                        "okr-alignment-report.json", "organization-health-report.json",
                        "workforce-plan-report.json", "financial-plan-report.json",
                        "cash-runway-report.json", "fundraising-readiness-report.json",
                        "governance-report.json", "enterprise-risk-report.json",
                        "board-effectiveness-report.json", "batch-15-conformance-report.json"));
    }

    public static ProgramDefinition agentWorkforce() {
        return definition(16, "AI-native company and Agent Workforce", "AI-native operating system",
                "ai-native-company-v1", "bounded-autonomous-company-ready",
                gates("AI16", "AI战略清晰", "Agent Workforce可治理", "人机责任清晰",
                        "模型和Agent风险受控", "自主执行安全", "组织转型可持续", "AI原生公司候选"),
                List.of("human-governance", "company-constitution", "autonomous-operations",
                        "agent-workforce", "human-workforce", "action-tools", "evidence-evaluation",
                        "learning-correction"),
                "ai-native-company",
                List.of("strategy", "work-design", "agent-workforce", "autonomous-operations",
                        "knowledge", "tools", "models", "evaluation", "security",
                        "workforce-transition", "functional-systems", "governance", "digital-twin", "reports"),
                List.of("ai-strategy-report.json", "automation-opportunity-report.json",
                        "workforce-redesign-report.json", "agent-portfolio-report.json",
                        "agent-performance-report.json", "agent-evaluation-report.json",
                        "model-risk-report.json", "agent-security-report.json",
                        "ai-cost-value-report.json", "workforce-transition-report.json",
                        "autonomous-operations-report.json", "board-ai-governance-report.json",
                        "batch-16-conformance-report.json"));
    }

    public static ProgramDefinition verticalSolutionFactory() {
        return definition(17, "Vertical Solution Factory", "VSP four-layer model",
                "vertical-solution-factory-v1", "vertical-commercial-delivery-ready",
                gates("V17", "领域模型成熟", "控制和证据完整", "行业Recipe可用", "行业验证可信",
                        "行业架构和交付就绪", "行业渠道就绪", "垂直版本商业交付候选"),
                List.of("shared-core", "industry-base-pack", "jurisdiction-overlay", "customer-extension",
                        "finance", "manufacturing", "energy", "healthcare", "government", "commerce", "telecom"),
                "vertical-solution-factory",
                List.of("core", "finance", "manufacturing", "energy", "healthcare", "government",
                        "commerce", "telecom", "jurisdictions", "marketplace", "partners", "reports"),
                List.of("vertical-readiness-report.json", "domain-coverage-report.json",
                        "regulatory-crosswalk-report.json", "industry-recipe-report.json",
                        "industry-evaluation-report.json", "regional-overlay-report.json",
                        "vertical-partner-report.json", "batch-17-conformance-report.json"));
    }

    public static ProgramDefinition groupIntegrationFactory() {
        return definition(18, "Group Integration Factory", "GITM", "group-integration-v1",
                "group-integration-completed",
                gates("M18", "交易和Day 1准备完成", "集团资产和依赖透明", "目标状态和处置决策完整",
                        "身份和数据整合安全", "整合Wave可生产运行", "TSA和旧系统可退出",
                        "协同收益已兑现", "集团整合正式完成"),
                List.of("business-capability", "application-portfolio", "data-domain", "identity",
                        "integration", "technology-standards", "infrastructure", "operating-model",
                        "governance", "synergy"),
                "group-integration-factory",
                List.of("deal-thesis", "clean-team", "day-one", "imo", "portfolio", "topology",
                        "target-state", "identity", "data", "integrations", "infrastructure",
                        "business-platforms", "migration-factory", "tsa", "carve-out", "synergy",
                        "change", "retirement", "reports"),
                List.of("day-one-readiness-report.json", "application-portfolio-report.json",
                        "duplicate-system-report.json", "target-architecture-report.json",
                        "identity-integration-report.json", "data-integration-report.json",
                        "tsa-exit-report.json", "migration-wave-report.json",
                        "synergy-realization-report.json", "stranded-cost-report.json",
                        "legacy-retirement-report.json", "batch-18-conformance-report.json"));
    }

    public static List<ProgramDefinition> all() {
        return List.of(companyOperatingSystem(), agentWorkforce(),
                verticalSolutionFactory(), groupIntegrationFactory());
    }

    private static ProgramDefinition definition(int batch, String title, String model,
                                                String version, String finalStatus,
                                                List<GateDefinition> gates, List<String> dimensions,
                                                String root, List<String> directories, List<String> reports) {
        return new ProgramDefinition(batch, title, model, version, finalStatus, gates,
                dimensions, root, directories, reports);
    }

    private static List<GateDefinition> gates(String prefix, String... labels) {
        return java.util.stream.IntStream.range(0, labels.length)
                .mapToObj(index -> new GateDefinition(prefix + "-" + (char) ('A' + index), labels[index]))
                .toList();
    }
}
