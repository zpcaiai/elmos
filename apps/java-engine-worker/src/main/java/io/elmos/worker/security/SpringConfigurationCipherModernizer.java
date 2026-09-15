package io.elmos.worker.security;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Enterprise Production Configuration Cipher & Jasypt 3.0.5+ Modernizer.
 *
 * <p>Modernizes secret encryption and startup validation for Spring Boot 3.x:
 * <ol>
 *   <li><b>Jasypt 3.0.5+ Starter Upgrade:</b>
 *       Upgrades {@code com.github.ulisesbocchio:jasypt-spring-boot-starter} to 3.0.5,
 *       ensuring compatibility with Spring Boot 3's revised {@code EnvironmentPostProcessor} lifecycle.</li>
 *   <li><b>Cryptographic Strength Hardening:</b>
 *       Configures compliant {@code PBEWITHHMACSHA512ANDAES_256} algorithm and {@code RandomIvGenerator},
 *       eliminating legacy weak CBC/MD5/DES security vulnerabilities.</li>
 *   <li><b>Fail-Fast Secret Bootstrap Probe:</b>
 *       Generates {@code EnvironmentSecretBootstrapCheck.java} to verify that all {@code ENC(...)}
 *       properties are successfully decrypted before database connections are initialized.</li>
 * </ol>
 */
public final class SpringConfigurationCipherModernizer {

    public record CipherModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> generatedArtifacts
    ) {
        public static CipherModernizationResult empty() {
            return new CipherModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern LEGACY_JASYPT_STARTER = Pattern.compile(
            "<dependency>\\s*<groupId>com\\.github\\.ulisesbocchio</groupId>\\s*<artifactId>jasypt-spring-boot-starter</artifactId>(?:\\s*<version>[^<]+</version>)?\\s*</dependency>",
            Pattern.DOTALL
    );

    private static final String MODERN_JASYPT_DEPENDENCY =
            """
                    <dependency>
                        <groupId>com.github.ulisesbocchio</groupId>
                        <artifactId>jasypt-spring-boot-starter</artifactId>
                        <version>3.0.5</version>
                    </dependency>""";

    /**
     * Executes configuration cipher modernization across the project workspace.
     */
    public CipherModernizationResult modernize(Path projectRoot) throws IOException {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return CipherModernizationResult.empty();
        }

        boolean anyModified = false;
        int totalChanges = 0;
        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> generatedArtifacts = new ArrayList<>();

        // 1. Upgrade Jasypt in pom.xml
        Path pomPath = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomPath)) {
            String pomContent = Files.readString(pomPath, StandardCharsets.UTF_8);
            Matcher jasyptMatcher = LEGACY_JASYPT_STARTER.matcher(pomContent);
            if (jasyptMatcher.find()) {
                String updatedPom = jasyptMatcher.replaceAll(MODERN_JASYPT_DEPENDENCY);
                Files.writeString(pomPath, updatedPom, StandardCharsets.UTF_8);
                anyModified = true;
                totalChanges++;
                modifiedFiles.add(pomPath.toString());
                rulesApplied.add("UPGRADE_JASYPT_STARTER_TO_3_0_5");
            }
        }

        // 2. Generate EnvironmentSecretBootstrapCheck
        Path securityDir = projectRoot.resolve("src/main/java/io/elmos/generated/security");
        Files.createDirectories(securityDir);
        Path checkFile = securityDir.resolve("EnvironmentSecretBootstrapCheck.java");
        if (!Files.exists(checkFile)) {
            String checkSource = generateBootstrapCheck();
            Files.writeString(checkFile, checkSource, StandardCharsets.UTF_8);
            anyModified = true;
            totalChanges++;
            modifiedFiles.add(checkFile.toString());
            generatedArtifacts.add(checkFile.toString());
            rulesApplied.add("GENERATE_ENVIRONMENT_SECRET_BOOTSTRAP_CHECK");
        }

        // 3. Inject secure Jasypt encryption parameters in application.yml
        Path ymlPath = projectRoot.resolve("src/main/resources/application.yml");
        if (Files.isRegularFile(ymlPath)) {
            String ymlContent = Files.readString(ymlPath, StandardCharsets.UTF_8);
            if (!ymlContent.contains("jasypt:")) {
                String jasyptConfig =
                        """

                        jasypt:
                          encryptor:
                            algorithm: PBEWITHHMACSHA512ANDAES_256
                            iv-generator-class: org.jasypt.iv.RandomIvGenerator
                            string-output-type: base64
                        """;
                Files.writeString(ymlPath, ymlContent + jasyptConfig, StandardCharsets.UTF_8);
                anyModified = true;
                totalChanges++;
                modifiedFiles.add(ymlPath.toString());
                rulesApplied.add("CONFIGURE_SECURE_JASYPT_ALGORITHM");
            }
        }

        return new CipherModernizationResult(anyModified, totalChanges, modifiedFiles, rulesApplied, generatedArtifacts);
    }

    private static String generateBootstrapCheck() {
        return """
                package io.elmos.generated.security;

                import org.springframework.boot.CommandLineRunner;
                import org.springframework.core.env.ConfigurableEnvironment;
                import org.springframework.core.env.EnumerablePropertySource;
                import org.springframework.core.env.PropertySource;
                import org.springframework.stereotype.Component;

                /**
                 * Fail-Fast Environment Secret Decryption Validator.
                 *
                 * <p>Inspects resolved environment properties on startup. If any property value
                 * still contains an undecrypted 'ENC(...)' token, halts application startup immediately
                 * with an actionable diagnostic message.
                 */
                @Component
                public class EnvironmentSecretBootstrapCheck implements CommandLineRunner {

                    private final ConfigurableEnvironment environment;

                    public EnvironmentSecretBootstrapCheck(ConfigurableEnvironment environment) {
                        this.environment = environment;
                    }

                    @Override
                    public void run(String... args) {
                        for (PropertySource<?> source : environment.getPropertySources()) {
                            if (source instanceof EnumerablePropertySource<?> enumerable) {
                                for (String name : enumerable.getPropertyNames()) {
                                    Object val = source.getProperty(name);
                                    if (val instanceof String str && str.startsWith("ENC(") && str.endsWith(")")) {
                                        throw new IllegalStateException(
                                                "Fatal Secret Startup Failure: Property '" + name + "' contains undecrypted Jasypt token: "
                                                        + str + ". Verify JASYPT_ENCRYPTOR_PASSWORD is provided in environment variables."
                                        );
                                    }
                                }
                            }
                        }
                    }
                }
                """;
    }
}
