package io.elmos.worker.rewrite;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.stream.Collectors;

/**
 * CLI and IPC standard-stream entry point for compiler-grade OpenRewrite AST execution.
 * Accepts JSON request from stdin or command arguments, invokes the typed
 * OpenRewriteAstCompiler engine, and emits structured JSON output to stdout.
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

            JsonNode request = MAPPER.readTree(inputJson);
            String recipeFamily = request.has("recipeFamily") ? request.get("recipeFamily").asText("SPRING_SECURITY_6") : "SPRING_SECURITY_6";
            String sourceCode = request.has("sourceCode") ? request.get("sourceCode").asText() : "";

            if (sourceCode.isBlank()) {
                ObjectNode emptyRes = MAPPER.createObjectNode();
                emptyRes.put("status", "SUCCESS");
                emptyRes.put("modified", false);
                emptyRes.put("sourceCode", "");
                emptyRes.putArray("recipesApplied");
                System.out.println(MAPPER.writeValueAsString(emptyRes));
                return;
            }

            OpenRewriteAstCompiler.AstRewriteResult result;
            if ("SPRING_SECURITY_6".equalsIgnoreCase(recipeFamily)) {
                result = OpenRewriteAstCompiler.modernizeSecurity(sourceCode);
            } else if ("JPA_HIBERNATE_6".equalsIgnoreCase(recipeFamily) || "HIBERNATE_6".equalsIgnoreCase(recipeFamily)) {
                result = OpenRewriteAstCompiler.modernizeJpaHibernate(sourceCode);
            } else if ("SPRING_CLOUD_2023".equalsIgnoreCase(recipeFamily) || "SPRING_CLOUD".equalsIgnoreCase(recipeFamily)) {
                result = OpenRewriteAstCompiler.modernizeSpringCloud(sourceCode);
            } else {
                // Default to security modernization if unknown
                result = OpenRewriteAstCompiler.modernizeSecurity(sourceCode);
            }

            ObjectNode response = MAPPER.createObjectNode();
            response.put("status", "SUCCESS");
            response.put("modified", result.modified());
            response.put("sourceCode", result.source());

            ArrayNode recipesArray = response.putArray("recipesApplied");
            for (String recipeName : result.recipesApplied()) {
                recipesArray.add(recipeName);
            }

            System.out.println(MAPPER.writeValueAsString(response));
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
     * Programmatic entry point for direct in-process invocations.
     */
    public static String processJson(String inputJson) throws Exception {
        JsonNode request = MAPPER.readTree(inputJson);
        String recipeFamily = request.has("recipeFamily") ? request.get("recipeFamily").asText("SPRING_SECURITY_6") : "SPRING_SECURITY_6";
        String sourceCode = request.has("sourceCode") ? request.get("sourceCode").asText() : "";

        OpenRewriteAstCompiler.AstRewriteResult result;
        if ("SPRING_SECURITY_6".equalsIgnoreCase(recipeFamily)) {
            result = OpenRewriteAstCompiler.modernizeSecurity(sourceCode);
        } else if ("JPA_HIBERNATE_6".equalsIgnoreCase(recipeFamily) || "HIBERNATE_6".equalsIgnoreCase(recipeFamily)) {
            result = OpenRewriteAstCompiler.modernizeJpaHibernate(sourceCode);
        } else if ("SPRING_CLOUD_2023".equalsIgnoreCase(recipeFamily) || "SPRING_CLOUD".equalsIgnoreCase(recipeFamily)) {
            result = OpenRewriteAstCompiler.modernizeSpringCloud(sourceCode);
        } else {
            result = OpenRewriteAstCompiler.modernizeSecurity(sourceCode);
        }

        ObjectNode response = MAPPER.createObjectNode();
        response.put("status", "SUCCESS");
        response.put("modified", result.modified());
        response.put("sourceCode", result.source());

        ArrayNode recipesArray = response.putArray("recipesApplied");
        for (String recipeName : result.recipesApplied()) {
            recipesArray.add(recipeName);
        }

        return MAPPER.writeValueAsString(response);
    }
}
