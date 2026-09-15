package io.elmos.worker.rewrite;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.elmos.worker.analysis.OpenRewriteAstAnalyzer;
import io.elmos.worker.cloud.SpringAlibabaDubboModernizer;
import io.elmos.worker.integration.SpringLegacyEnterpriseIntegrationModernizer;
import io.elmos.worker.security.SpringLegacySecurityModernizer;
import io.elmos.worker.security.SpringSecurityCorsCsrfAdvancedModernizer;
import io.elmos.worker.security.SpringSecurityFilterLifecycleModernizer;
import io.elmos.worker.testing.SpringJUnitModernizer;
import io.elmos.worker.transaction.SpringTransactionAndDataIsolationModernizer;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

/**
 * CLI and IPC standard-stream entry point for compiler-grade OpenRewrite AST execution and analysis.
 * Accepts JSON request from stdin or command arguments, invokes the typed
 * OpenRewrite compiler/analyzer engines, and emits structured JSON output to stdout.
 */
public class OpenRewriteCli {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    public static void main(String[] args) {
        try {
            String inputJson;
            if (args.length > 0 && !args[0].isBlank()) {
                inputJson = args[0];
            } else {
                try (BufferedReader reader = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
                    inputJson = reader.lines().collect(Collectors.joining("\n"));
                }
            }

            if (inputJson == null || inputJson.isBlank()) {
                System.err.println("Error: Empty input provided to OpenRewriteCli");
                System.exit(1);
                return;
            }

            String responseJson = processJson(inputJson);
            System.out.println(responseJson);
            System.exit(0);

        } catch (Exception e) {
            try {
                ObjectNode errNode = MAPPER.createObjectNode();
                errNode.put("status", "ERROR");
                errNode.put("errorMessage", e.getMessage() != null ? e.getMessage() : e.toString());
                System.err.println(MAPPER.writeValueAsString(errNode));
            } catch (Exception ignored) {
                System.err.println("{\"status\":\"ERROR\",\"errorMessage\":\"" + e.getMessage() + "\"}");
            }
            System.exit(2);
        }
    }

    /**
     * Programmatic entry point for direct in-process or IPC invocations.
     */
    public static String processJson(String inputJson) throws Exception {
        JsonNode request = MAPPER.readTree(inputJson);

        String action = request.has("action") ? request.get("action").asText("rewrite") : "rewrite";
        String sourceCode = request.has("sourceCode") ? request.get("sourceCode").asText() : "";

        if ("analyze".equalsIgnoreCase(action)) {
            return handleAnalyze(request, sourceCode);
        } else {
            return handleRewrite(request, sourceCode);
        }
    }

    private static String handleAnalyze(JsonNode request, String sourceCode) throws Exception {
        String analysisType = request.has("analysisType") ? request.get("analysisType").asText("ALL") : "ALL";

        OpenRewriteAstAnalyzer.AnalysisReport report = OpenRewriteAstAnalyzer.analyze(sourceCode, analysisType);

        ObjectNode response = MAPPER.createObjectNode();
        response.put("status", report.status());
        response.put("findingsCount", report.findingsCount());
        response.put("durationMs", report.durationMs());

        ArrayNode findingsArray = response.putArray("findings");
        for (OpenRewriteAstAnalyzer.AstFinding finding : report.findings()) {
            ObjectNode fNode = findingsArray.addObject();
            fNode.put("ruleId", finding.ruleId());
            fNode.put("severity", finding.severity());
            fNode.put("location", finding.location());
            fNode.put("message", finding.message());
            fNode.put("remediation", finding.remediation());
        }

        return MAPPER.writeValueAsString(response);
    }

    private static String handleRewrite(JsonNode request, String sourceCode) throws Exception {
        if (sourceCode.isBlank()) {
            ObjectNode emptyRes = MAPPER.createObjectNode();
            emptyRes.put("status", "SUCCESS");
            emptyRes.put("modified", false);
            emptyRes.put("sourceCode", "");
            emptyRes.putArray("recipesApplied");
            return MAPPER.writeValueAsString(emptyRes);
        }

        String recipeFamily = request.has("recipeFamily") ? request.get("recipeFamily").asText("SPRING_SECURITY_6") : "SPRING_SECURITY_6";
        String currentCode = sourceCode;
        List<String> allApplied = new ArrayList<>();
        boolean anyModified = false;

        if ("ALL".equalsIgnoreCase(recipeFamily) || "AUTO".equalsIgnoreCase(recipeFamily)) {
            // 1. Spring Security 6
            var secRes = OpenRewriteAstCompiler.modernizeSecurity(currentCode);
            if (secRes.modified()) {
                currentCode = secRes.source();
                allApplied.addAll(secRes.recipesApplied());
                anyModified = true;
            }

            // 2. JPA & Hibernate 6
            var jpaRes = OpenRewriteAstCompiler.modernizeJpaHibernate(currentCode);
            if (jpaRes.modified()) {
                currentCode = jpaRes.source();
                allApplied.addAll(jpaRes.recipesApplied());
                anyModified = true;
            }

            // 3. Spring Cloud 2023+
            var cloudRes = OpenRewriteAstCompiler.modernizeSpringCloud(currentCode);
            if (cloudRes.modified()) {
                currentCode = cloudRes.source();
                allApplied.addAll(cloudRes.recipesApplied());
                anyModified = true;
            }

            // 4. JUnit 5 Modernization
            if (SpringJUnitModernizer.isLegacyJunit4Test(currentCode)) {
                List<String> junitRules = new ArrayList<>();
                String modernizedJunit = SpringJUnitModernizer.modernizeTestContent(currentCode, junitRules);
                if (!modernizedJunit.equals(currentCode)) {
                    currentCode = modernizedJunit;
                    allApplied.addAll(junitRules);
                    anyModified = true;
                }
            }

            // 5. Transaction & Data Isolation
            var txRes = SpringTransactionAndDataIsolationModernizer.modernizeContent(currentCode, "VirtualSource.java");
            if (txRes.modified() && !txRes.rulesApplied().isEmpty()) {
                currentCode = txRes.rulesApplied().get(0);
                allApplied.addAll(txRes.rulesApplied().subList(1, txRes.rulesApplied().size()));
                anyModified = true;
            }

            // 6. Dubbo 3 Modernization
            List<String> dubboRules = new ArrayList<>();
            String dubboCode = SpringAlibabaDubboModernizer.modernizeJavaSource(currentCode, dubboRules);
            if (!dubboCode.equals(currentCode)) {
                currentCode = dubboCode;
                allApplied.addAll(dubboRules);
                anyModified = true;
            }

            // 7. Enterprise Integrations (JAX-WS, DWR, JSF)
            List<String> eiRules = new ArrayList<>();
            List<String> eiBlockers = new ArrayList<>();
            String eiCode = SpringLegacyEnterpriseIntegrationModernizer.modernizeJavaSource(currentCode, eiRules, eiBlockers);
            if (!eiCode.equals(currentCode)) {
                currentCode = eiCode;
                allApplied.addAll(eiRules);
                anyModified = true;
            }

            // 8. Legacy Security (OAuth2, Shiro)
            List<String> secRules = new ArrayList<>();
            List<String> secBlockers = new ArrayList<>();
            String secCode = SpringLegacySecurityModernizer.modernizeJavaSource(currentCode, secRules, secBlockers);
            if (!secCode.equals(currentCode)) {
                currentCode = secCode;
                allApplied.addAll(secRules);
                anyModified = true;
            }

            // 9. SPA CSRF Handshake
            var csrfRes = SpringSecurityCorsCsrfAdvancedModernizer.modernizeContent(currentCode);
            if (csrfRes.modified() && !csrfRes.rulesApplied().isEmpty()) {
                currentCode = csrfRes.rulesApplied().get(0);
                allApplied.addAll(csrfRes.rulesApplied().subList(1, csrfRes.rulesApplied().size()));
                anyModified = true;
            }

        } else if ("SPRING_SECURITY_6".equalsIgnoreCase(recipeFamily)) {
            var res = OpenRewriteAstCompiler.modernizeSecurity(currentCode);
            currentCode = res.source();
            allApplied.addAll(res.recipesApplied());
            anyModified = res.modified();

        } else if ("SECURITY_FILTER_LIFECYCLE".equalsIgnoreCase(recipeFamily)) {
            String filterName = request.has("filterTypeName") ? request.get("filterTypeName").asText("JwtAuthenticationFilter") : "JwtAuthenticationFilter";
            String updated = SpringSecurityFilterLifecycleModernizer.modernizeContent(currentCode, filterName);
            if (!updated.equals(currentCode)) {
                currentCode = updated;
                allApplied.add("SEC-050: Generated FilterRegistrationBean with setEnabled(false) for " + filterName);
                anyModified = true;
            }

        } else if ("SPA_CSRF_HANDSHAKE".equalsIgnoreCase(recipeFamily) || "CORS_CSRF".equalsIgnoreCase(recipeFamily)) {
            var csrfRes = SpringSecurityCorsCsrfAdvancedModernizer.modernizeContent(currentCode);
            if (csrfRes.modified() && !csrfRes.rulesApplied().isEmpty()) {
                currentCode = csrfRes.rulesApplied().get(0);
                allApplied.addAll(csrfRes.rulesApplied().subList(1, csrfRes.rulesApplied().size()));
                anyModified = true;
            }

        } else if ("DUBBO_3".equalsIgnoreCase(recipeFamily) || "DUBBO".equalsIgnoreCase(recipeFamily)) {
            List<String> dubboRules = new ArrayList<>();
            String updated = SpringAlibabaDubboModernizer.modernizeJavaSource(currentCode, dubboRules);
            if (!updated.equals(currentCode)) {
                currentCode = updated;
                allApplied.addAll(dubboRules);
                anyModified = true;
            }

        } else if ("ENTERPRISE_INTEGRATION".equalsIgnoreCase(recipeFamily) || "SOAP_DWR_JSF".equalsIgnoreCase(recipeFamily)) {
            List<String> eiRules = new ArrayList<>();
            List<String> eiBlockers = new ArrayList<>();
            String updated = SpringLegacyEnterpriseIntegrationModernizer.modernizeJavaSource(currentCode, eiRules, eiBlockers);
            if (!updated.equals(currentCode)) {
                currentCode = updated;
                allApplied.addAll(eiRules);
                anyModified = true;
            }

        } else if ("LEGACY_SECURITY".equalsIgnoreCase(recipeFamily) || "SHIRO_OAUTH2".equalsIgnoreCase(recipeFamily)) {
            List<String> secRules = new ArrayList<>();
            List<String> secBlockers = new ArrayList<>();
            String updated = SpringLegacySecurityModernizer.modernizeJavaSource(currentCode, secRules, secBlockers);
            if (!updated.equals(currentCode)) {
                currentCode = updated;
                allApplied.addAll(secRules);
                anyModified = true;
            }

        } else if ("JPA_HIBERNATE_6".equalsIgnoreCase(recipeFamily) || "HIBERNATE_6".equalsIgnoreCase(recipeFamily)) {
            var res = OpenRewriteAstCompiler.modernizeJpaHibernate(currentCode);
            currentCode = res.source();
            allApplied.addAll(res.recipesApplied());
            anyModified = res.modified();

        } else if ("SPRING_CLOUD_2023".equalsIgnoreCase(recipeFamily) || "SPRING_CLOUD".equalsIgnoreCase(recipeFamily)) {
            var res = OpenRewriteAstCompiler.modernizeSpringCloud(currentCode);
            currentCode = res.source();
            allApplied.addAll(res.recipesApplied());
            anyModified = res.modified();

        } else if ("JUNIT_5".equalsIgnoreCase(recipeFamily) || "TESTING".equalsIgnoreCase(recipeFamily)) {
            List<String> junitRules = new ArrayList<>();
            String modernizedJunit = SpringJUnitModernizer.modernizeTestContent(currentCode, junitRules);
            if (!modernizedJunit.equals(currentCode)) {
                currentCode = modernizedJunit;
                allApplied.addAll(junitRules);
                anyModified = true;
            }

        } else if ("TRANSACTION_ISOLATION".equalsIgnoreCase(recipeFamily)) {
            var txRes = SpringTransactionAndDataIsolationModernizer.modernizeContent(currentCode, "VirtualSource.java");
            if (txRes.modified() && !txRes.rulesApplied().isEmpty()) {
                currentCode = txRes.rulesApplied().get(0);
                allApplied.addAll(txRes.rulesApplied().subList(1, txRes.rulesApplied().size()));
                anyModified = true;
            }

        } else {
            // Default to Security
            var res = OpenRewriteAstCompiler.modernizeSecurity(currentCode);
            currentCode = res.source();
            allApplied.addAll(res.recipesApplied());
            anyModified = res.modified();
        }

        ObjectNode response = MAPPER.createObjectNode();
        response.put("status", "SUCCESS");
        response.put("modified", anyModified);
        response.put("sourceCode", currentCode);

        ArrayNode recipesArray = response.putArray("recipesApplied");
        for (String recipeName : allApplied) {
            recipesArray.add(recipeName);
        }

        return MAPPER.writeValueAsString(response);
    }
}
