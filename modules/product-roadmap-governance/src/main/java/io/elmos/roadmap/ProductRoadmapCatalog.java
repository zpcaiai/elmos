package io.elmos.roadmap;

import java.util.List;

import static io.elmos.roadmap.ProductRoadmapModels.*;

/** Authoritative names and sequential gates extracted from the product Batch 27-34 source. */
public final class ProductRoadmapCatalog {
    private ProductRoadmapCatalog() {}

    private static final List<String> COMMON_PROHIBITIONS = List.of(
            "AUTO_APPROVE_FINANCIAL_OR_ACCOUNTING_DECISION",
            "AUTO_DECIDE_EMPLOYMENT_OR_INDIVIDUAL_PERFORMANCE",
            "AUTO_EXECUTE_PRODUCTION_CHANGE",
            "AUTO_GRANT_PRIVILEGED_ACCESS",
            "AUTO_DECLARE_BENEFIT_OR_TRANSFORMATION_SUCCESS",
            "EXECUTE_EXTERNAL_OPERATION_FROM_CONTROL_PLANE");

    public static List<BatchDefinition> all() {
        return List.of(
                definition(27, "Technology Business Management and Digital Product Investment Governance",
                        18, 56, "TBM27", "financial-source-reconciliation", "taxonomy-and-allocation",
                        "product-cost-and-unit-economics", "funding-and-capitalization-controls",
                        "benefit-and-technical-debt-evidence", "investment-human-decision-package"),
                definition(28, "Organization Capability, Talent and Technology Workforce Modernization",
                        18, 56, "ORG28", "privacy-and-source-admission", "organization-and-work-discovery",
                        "skills-and-capability-evidence", "workforce-scenario-and-fairness",
                        "human-accountability-and-appeal", "organization-outcome-decision-package"),
                definition(29, "Enterprise Transformation Execution and Change Management",
                        18, 70, "TRN29", "strategy-and-portfolio-alignment", "dependency-and-capacity",
                        "stakeholder-and-change-impact", "adoption-and-readiness",
                        "wave-cutover-and-hypercare-evidence", "benefit-and-closure-human-decision"),
                definition(30, "Integrated Autonomous Modernization Control Tower",
                        18, 70, "CTL30", "identity-resolution-and-provenance", "digital-twin-reconciliation",
                        "workflow-agent-and-policy-controls", "scenario-and-plan-validation",
                        "transaction-compensation-and-replay", "human-command-and-resilience-decision"),
                definition(31, "ELMOS Reference Implementation and MVP Engineering",
                        18, 32, "MVP31", "toolchain-and-module-baseline", "tenant-scm-runner-security",
                        "snapshot-and-workflow-durability", "java-health-plan-and-rewrite",
                        "independent-build-test-compatibility", "pr-evidence-and-production-readiness"),
                definition(32, "MVP Scaffold Independent Gap Review and Remediation",
                        0, 32, "AUD32", "claimed-artifact-inventory", "security-gap-review",
                        "runner-and-workflow-reliability", "deterministic-java-capability-review",
                        "supply-chain-and-e2e-remediation", "independent-mvp-readiness-review"),
                definition(33, "Secure Java Modernization Paid Vertical Loop",
                        35, 18, "JVM33", "oidc-tenant-rls-foundation", "github-runner-and-sandbox",
                        "immutable-snapshot-and-maven-baseline", "health-plan-and-openrewrite",
                        "compile-test-agent-and-temporal", "pr-evidence-security-and-commercial-gate"),
                definition(34, "Enterprise Identity, Multi-tenant and Access Governance",
                        40, 20, "IAM34", "federated-human-identity", "tenant-membership-and-rls",
                        "rbac-abac-and-resource-authorization", "saml-scim-and-offboarding",
                        "workload-credential-and-privileged-access", "access-review-incident-and-release-gate"));
    }

    public static BatchDefinition require(int batch) {
        return all().stream().filter(value -> value.batch() == batch).findFirst()
                .orElseThrow(() -> new IllegalArgumentException("unknown product batch: " + batch));
    }

    private static BatchDefinition definition(int batch, String title, int skills, int scenarios,
                                              String prefix, String... labels) {
        List<GateDefinition> gates = java.util.stream.IntStream.range(0, labels.length)
                .mapToObj(index -> new GateDefinition(prefix + "-" + (char) ('A' + index), labels[index]))
                .toList();
        return new BatchDefinition(batch, title, "elmos-product-batch-" + batch + "-v1",
                skills, scenarios, gates, COMMON_PROHIBITIONS);
    }
}
