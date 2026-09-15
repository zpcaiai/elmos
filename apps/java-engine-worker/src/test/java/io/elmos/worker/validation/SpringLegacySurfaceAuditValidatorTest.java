package io.elmos.worker.validation;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringLegacySurfaceAuditValidatorTest {
    @TempDir Path root;

    @Test void blocksUnmigratedLegacySecurityRpcWebAndDubboSurfaces() throws Exception {
        Files.writeString(root.resolve("pom.xml"), """
                <project><dependency><groupId>org.springframework.security.oauth</groupId>
                <artifactId>spring-security-oauth2</artifactId></dependency></project>
                """);
        Files.writeString(root.resolve("dubbo.xml"), "<dubbo:service interface=\"x.Api\" ref=\"api\"/>");
        Files.writeString(root.resolve("RemoteConfig.java"), "class RemoteConfig { RmiServiceExporter exporter; }");

        var report = new SpringLegacySurfaceAuditValidator().auditProject(root);

        assertFalse(report.compliant());
        assertTrue(report.violations().stream().anyMatch(item -> item.ruleId().equals("LEGACY-OAUTH2-DEPENDENCY")));
        assertTrue(report.violations().stream().anyMatch(item -> item.ruleId().equals("LEGACY-DUBBO-XML-SERVICE")));
        assertTrue(report.violations().stream().anyMatch(item -> item.ruleId().equals("LEGACY-RMI")));
    }

    @Test void acceptsModernizedTargetWithoutLegacyTokens() throws Exception {
        Files.writeString(root.resolve("SecurityConfig.java"), """
                import org.springframework.security.web.SecurityFilterChain;
                class SecurityConfig { SecurityFilterChain chain; }
                """);
        var report = new SpringLegacySurfaceAuditValidator().auditProject(root);
        assertTrue(report.compliant());
    }

    @Test void onlyFlagsShiroOneOnItsExactDependencyAndIgnoresBuildOutputs() throws Exception {
        Files.writeString(root.resolve("pom.xml"), """
                <project><dependencies>
                  <dependency><groupId>org.apache.shiro</groupId><artifactId>shiro-spring-boot-web-starter</artifactId><version>3.0.1</version></dependency>
                  <dependency><groupId>com.acme</groupId><artifactId>legacy-helper</artifactId><version>1.2.3</version></dependency>
                </dependencies></project>
                """);
        Path generated = root.resolve("target/generated-sources/Legacy.java");
        Files.createDirectories(generated.getParent());
        Files.writeString(generated, "class Legacy { RmiServiceExporter exporter; }");

        var report = new SpringLegacySurfaceAuditValidator().auditProject(root);

        assertTrue(report.compliant());
    }

    @Test void flagsExactShiroOneDependency() throws Exception {
        Files.writeString(root.resolve("pom.xml"), """
                <project><dependency><groupId>org.apache.shiro</groupId>
                  <artifactId>shiro-spring</artifactId><version>1.13.0</version></dependency></project>
                """);

        var report = new SpringLegacySurfaceAuditValidator().auditProject(root);

        assertTrue(report.violations().stream().anyMatch(item -> item.ruleId().equals("LEGACY-SHIRO-1")));
    }
}
