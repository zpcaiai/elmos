package io.elmos.worker.validation;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.regex.Pattern;

/** Detects legacy enterprise surfaces that must not disappear behind a green core audit. */
public final class SpringLegacySurfaceAuditValidator {
    public record Violation(String ruleId, String filePath, String message) {}
    public record AuditReport(boolean compliant, double complianceScore, List<Violation> violations) {}

    private record Rule(String id, String needle, String message) {}

    private static final List<Rule> RULES = List.of(
            new Rule("LEGACY-AXIS", "org.apache.axis", "Axis SOAP runtime remains on a pre-Jakarta stack"),
            new Rule("LEGACY-OAUTH2-DEPENDENCY", "org.springframework.security.oauth", "legacy spring-security-oauth2 remains"),
            new Rule("LEGACY-AUTHORIZATION-SERVER", "@EnableAuthorizationServer", "legacy OAuth2 authorization server remains"),
            new Rule("LEGACY-RESOURCE-SERVER", "@EnableResourceServer", "legacy OAuth2 resource server remains"),
            new Rule("LEGACY-DWR", "org.directwebremoting", "DWR remote exposure remains"),
            new Rule("LEGACY-JSF-BEAN", "javax.faces.bean", "JSF managed bean uses the removed javax.faces bean model"),
            new Rule("LEGACY-DUBBO-XML-SERVICE", "<dubbo:service", "Dubbo XML service export remains"),
            new Rule("LEGACY-DUBBO-XML-REFERENCE", "<dubbo:reference", "Dubbo XML reference remains"),
            new Rule("LEGACY-RMI", "RmiServiceExporter", "Java RMI exporter requires a retained compatibility boundary"),
            new Rule("LEGACY-HTTP-INVOKER", "HttpInvokerServiceExporter", "Spring HTTP Invoker uses Java serialization"),
            new Rule("LEGACY-HESSIAN", "HessianServiceExporter", "Hessian remote serialization remains"),
            new Rule("LEGACY-BURLAP", "BurlapServiceExporter", "Burlap remote serialization remains")
    );
    private static final Pattern SHIRO_ONE_DEPENDENCY = Pattern.compile(
            "(?s)<dependency>\\s*<groupId>org\\.apache\\.shiro</groupId>"
                    + "(?:(?!</dependency>).)*?<version>1(?:\\.[^<]*)?</version>"
                    + "(?:(?!</dependency>).)*?</dependency>");

    public AuditReport auditProject(Path projectRoot) throws IOException {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        List<Violation> violations = new ArrayList<>();
        if (!Files.isDirectory(projectRoot)) return new AuditReport(true, 100.0, List.of());
        try (var stream = Files.walk(projectRoot)) {
            for (Path file : stream.filter(Files::isRegularFile)
                    .filter(file -> !ignored(projectRoot, file))
                    .filter(SpringLegacySurfaceAuditValidator::sourceLike).toList()) {
                String text = Files.readString(file, StandardCharsets.UTF_8);
                for (Rule rule : RULES) {
                    if (!text.contains(rule.needle())) continue;
                    violations.add(new Violation(rule.id(), relative(projectRoot, file), rule.message()));
                }
                if (SHIRO_ONE_DEPENDENCY.matcher(text).find()) {
                    violations.add(new Violation("LEGACY-SHIRO-1", relative(projectRoot, file),
                            "Shiro 1 dependency remains on the pre-Jakarta generation"));
                }
            }
        }
        double score = Math.max(0.0, 100.0 - violations.size() * 15.0);
        return new AuditReport(violations.isEmpty(), score, List.copyOf(violations));
    }

    private static boolean sourceLike(Path file) {
        String name = file.getFileName().toString();
        return name.endsWith(".java") || name.endsWith(".xml") || name.endsWith(".gradle")
                || name.endsWith(".kts") || name.endsWith(".properties") || name.endsWith(".yml")
                || name.endsWith(".yaml");
    }

    private static boolean ignored(Path root, Path file) {
        for (Path part : root.relativize(file)) {
            String name = part.toString();
            if (name.equals("target") || name.equals("build") || name.equals(".git")) return true;
        }
        return false;
    }

    private static String relative(Path root, Path file) {
        return root.relativize(file).toString().replace('\\', '/');
    }
}
