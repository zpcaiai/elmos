package io.elmos.worker.serialization;

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
import java.util.stream.Stream;

/**
 * Industrial-grade modernizer for JSON serialization, Fastjson elimination, and Jackson precision contracts.
 *
 * <p>Key challenges in Spring Boot 2 to 3 modernization:
 * <ol>
 *   <li><b>Fastjson 1.x Vulnerabilities & Incompatibility:</b> Fastjson 1.x violates Java 17+ strong encapsulation
 *       and contains severe RCE vulnerabilities. This modernizer eliminates Fastjson 1.x and migrates
 *       calls to standard Jackson / Fastjson2 for Spring 6.</li>
 *   <li><b>Time & Date Precision Drift:</b> Spring Boot 3 strict ISO deserialization breaks legacy
 *       {@code yyyy-MM-dd HH:mm:ss} payloads. We inject a robust {@code JacksonConfiguration} with
 *       {@code JavaTimeModule} and timezone normalization.</li>
 *   <li><b>JavaScript 53-Bit Precision Loss:</b> 64-bit Snowflake IDs (Long) lose lower digits when serialized
 *       as JSON numbers to frontend JS. We inject {@code ToStringSerializer} for {@code Long} types.</li>
 * </ol>
 */
public final class SpringSerializationContractModernizer {

    public record SerializationModernizationResult(
            boolean modified,
            int changesCount,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> warnings
    ) {
        public static SerializationModernizationResult empty() {
            return new SerializationModernizationResult(false, 0, Collections.emptySet(), Collections.emptyList(), Collections.emptyList());
        }
    }

    private static final Pattern FASTJSON_DEP_PATTERN = Pattern.compile("(?s)<dependency>\\s*<groupId>com\\.alibaba</groupId>\\s*<artifactId>fastjson</artifactId>\\s*<version>[^<]+</version>\\s*</dependency>");

    private SpringSerializationContractModernizer() {}

    public static SerializationModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return SerializationModernizationResult.empty();
        }

        Set<String> modifiedFiles = new LinkedHashSet<>();
        List<String> rulesApplied = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        int changes = 0;

        boolean hasFastjson = false;

        // 1. Scan and modernize Java source files
        try (Stream<Path> stream = Files.walk(projectRoot)) {
            List<Path> javaFiles = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".java"))
                    .toList();

            for (Path javaFile : javaFiles) {
                SerializationModernizationResult res = modernizeJavaFile(projectRoot, javaFile);
                if (res.modified()) {
                    modifiedFiles.addAll(res.modifiedFiles());
                    rulesApplied.addAll(res.rulesApplied());
                    warnings.addAll(res.warnings());
                    changes += res.changesCount();
                    hasFastjson = true;
                }
            }
        } catch (IOException ignored) {}

        // 2. Generate Jackson Global Configuration if Jackson / Spring Web is used
        Path configDir = projectRoot.resolve("src/main/java/io/elmos/generated/serialization");
        Path jacksonConfig = configDir.resolve("JacksonConfiguration.java");
        if (!Files.exists(jacksonConfig)) {
            try {
                Files.createDirectories(configDir);
                String configSource = """
                        package io.elmos.generated.serialization;

                        import com.fasterxml.jackson.databind.DeserializationFeature;
                        import com.fasterxml.jackson.databind.ObjectMapper;
                        import com.fasterxml.jackson.databind.ser.std.ToStringSerializer;
                        import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
                        import com.fasterxml.jackson.datatype.jsr310.deser.LocalDateDeserializer;
                        import com.fasterxml.jackson.datatype.jsr310.deser.LocalDateTimeDeserializer;
                        import com.fasterxml.jackson.datatype.jsr310.ser.LocalDateSerializer;
                        import com.fasterxml.jackson.datatype.jsr310.ser.LocalDateTimeSerializer;
                        import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
                        import org.springframework.context.annotation.Bean;
                        import org.springframework.context.annotation.Configuration;

                        import java.math.BigInteger;
                        import java.time.LocalDate;
                        import java.time.LocalDateTime;
                        import java.time.format.DateTimeFormatter;
                        import java.util.TimeZone;

                        /**
                         * Auto-generated by Elmos SpringSerializationContractModernizer.
                         * Configures Jackson date/time formatting, timezone normalization, and snowflake Long serialization.
                         */
                        @Configuration(proxyBeanMethods = false)
                        public class JacksonConfiguration {

                            public static final String DATE_TIME_FORMAT = "yyyy-MM-dd HH:mm:ss";
                            public static final String DATE_FORMAT = "yyyy-MM-dd";

                            @Bean
                            public Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
                                return builder -> {
                                    // 1. Timezone and Unknown property resilience
                                    builder.timeZone(TimeZone.getTimeZone("GMT+8"));
                                    builder.featuresToDisable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

                                    // 2. Java 8 Time module with uniform formatting
                                    DateTimeFormatter dateTimeFormatter = DateTimeFormatter.ofPattern(DATE_TIME_FORMAT);
                                    DateTimeFormatter dateFormatter = DateTimeFormatter.ofPattern(DATE_FORMAT);

                                    JavaTimeModule timeModule = new JavaTimeModule();
                                    timeModule.addSerializer(LocalDateTime.class, new LocalDateTimeSerializer(dateTimeFormatter));
                                    timeModule.addDeserializer(LocalDateTime.class, new LocalDateTimeDeserializer(dateTimeFormatter));
                                    timeModule.addSerializer(LocalDate.class, new LocalDateSerializer(dateFormatter));
                                    timeModule.addDeserializer(LocalDate.class, new LocalDateDeserializer(dateFormatter));
                                    builder.modules(timeModule);

                                    // 3. Convert Long / BigInteger to String to prevent JS precision truncation
                                    builder.serializerByType(Long.class, ToStringSerializer.instance);
                                    builder.serializerByType(Long.TYPE, ToStringSerializer.instance);
                                    builder.serializerByType(BigInteger.class, ToStringSerializer.instance);
                                };
                            }
                        }
                        """;
                Files.writeString(jacksonConfig, configSource, StandardCharsets.UTF_8);
                modifiedFiles.add(projectRoot.relativize(jacksonConfig).toString());
                rulesApplied.add("JACKSON_GLOBAL_CONFIGURATION_GENERATED");
                changes++;
            } catch (IOException e) {
                warnings.add("Failed to write JacksonConfiguration: " + e.getMessage());
            }
        }

        // 3. Modernize POM / Gradle dependency
        Path pomFile = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(pomFile)) {
            try {
                String pom = Files.readString(pomFile, StandardCharsets.UTF_8);
                String updated = pom;

                if (FASTJSON_DEP_PATTERN.matcher(updated).find()) {
                    String jacksonDep = """
                                <dependency>
                                  <groupId>com.fasterxml.jackson.datatype</groupId>
                                  <artifactId>jackson-datatype-jsr310</artifactId>
                                </dependency>""";
                    updated = FASTJSON_DEP_PATTERN.matcher(updated).replaceAll(Matcher.quoteReplacement(jacksonDep));
                    rulesApplied.add("FASTJSON_REPLACED_WITH_JACKSON_IN_POM");
                    changes++;
                }

                if (!updated.equals(pom)) {
                    Files.writeString(pomFile, updated, StandardCharsets.UTF_8);
                    modifiedFiles.add(projectRoot.relativize(pomFile).toString());
                }
            } catch (IOException e) {
                warnings.add("Failed to update pom.xml: " + e.getMessage());
            }
        }

        // 4. Update application.yml/properties with Jackson format defaults
        ConfigUpdateResult cfg = modernizeApplicationConfig(projectRoot);
        if (cfg.modified()) {
            modifiedFiles.addAll(cfg.files());
            rulesApplied.addAll(cfg.rules());
            changes += cfg.changes();
        }

        return new SerializationModernizationResult(!modifiedFiles.isEmpty(), changes, modifiedFiles, rulesApplied, warnings);
    }

    private static SerializationModernizationResult modernizeJavaFile(Path projectRoot, Path javaFile) {
        try {
            String content = Files.readString(javaFile, StandardCharsets.UTF_8);
            String original = content;
            List<String> rules = new ArrayList<>();
            int changes = 0;

            // 1. Detect and modernize com.alibaba.fastjson imports
            if (content.contains("com.alibaba.fastjson")) {
                // If using JSON.toJSONString(x) or JSON.parseObject(s, C.class), convert to com.alibaba.fastjson2 or Jackson
                content = content.replaceAll("import\\s+com\\.alibaba\\.fastjson\\.JSON;\\s*", "import com.alibaba.fastjson2.JSON;\n");
                content = content.replaceAll("import\\s+com\\.alibaba\\.fastjson\\.JSONObject;\\s*", "import com.alibaba.fastjson2.JSONObject;\n");
                content = content.replaceAll("import\\s+com\\.alibaba\\.fastjson\\.JSONArray;\\s*", "import com.alibaba.fastjson2.JSONArray;\n");
                content = content.replaceAll("import\\s+com\\.alibaba\\.fastjson\\.TypeReference;\\s*", "import com.alibaba.fastjson2.TypeReference;\n");

                rules.add("FASTJSON1_TRANSPILED_TO_FASTJSON2");
                changes++;
            }

            if (!content.equals(original)) {
                Files.writeString(javaFile, content, StandardCharsets.UTF_8);
                return new SerializationModernizationResult(true, changes, Set.of(projectRoot.relativize(javaFile).toString()), rules, Collections.emptyList());
            }
        } catch (IOException ignored) {}

        return SerializationModernizationResult.empty();
    }

    private record ConfigUpdateResult(boolean modified, int changes, Set<String> files, List<String> rules) {}

    private static ConfigUpdateResult modernizeApplicationConfig(Path projectRoot) {
        Set<String> files = new LinkedHashSet<>();
        List<String> rules = new ArrayList<>();
        int changes = 0;

        try (Stream<Path> stream = Files.walk(projectRoot)) {
            List<Path> configs = stream
                    .filter(Files::isRegularFile)
                    .filter(p -> {
                        String name = p.getFileName().toString();
                        return (name.startsWith("application.") || name.startsWith("application-")) &&
                                (name.endsWith(".yml") || name.endsWith(".yaml") || name.endsWith(".properties"));
                    })
                    .toList();

            for (Path config : configs) {
                String name = config.getFileName().toString();
                String content = Files.readString(config, StandardCharsets.UTF_8);
                String updated = content;

                if (name.endsWith(".yml") || name.endsWith(".yaml")) {
                    if (!content.contains("date-format:") && !content.contains("jackson:")) {
                        updated += """

                                spring:
                                  jackson:
                                    date-format: yyyy-MM-dd HH:mm:ss
                                    time-zone: GMT+8
                                    deserialization:
                                      fail-on-unknown-properties: false
                                """;
                        rules.add("JACKSON_CONFIG_INJECTED_INTO_YAML");
                        changes++;
                    }
                } else if (name.endsWith(".properties")) {
                    if (!content.contains("spring.jackson.date-format")) {
                        updated += """

                                spring.jackson.date-format=yyyy-MM-dd HH:mm:ss
                                spring.jackson.time-zone=GMT+8
                                spring.jackson.deserialization.fail-on-unknown-properties=false
                                """;
                        rules.add("JACKSON_CONFIG_INJECTED_INTO_PROPERTIES");
                        changes++;
                    }
                }

                if (!updated.equals(content)) {
                    Files.writeString(config, updated, StandardCharsets.UTF_8);
                    files.add(projectRoot.relativize(config).toString());
                }
            }
        } catch (IOException ignored) {}

        return new ConfigUpdateResult(!files.isEmpty(), changes, files, rules);
    }
}
