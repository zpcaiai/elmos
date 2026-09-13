package io.elmos.worker.messaging;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Safe dependency, namespace, and configuration migration from ActiveMQ Classic to Artemis. */
public final class SpringActiveMqToArtemisModernizer {
    public record ModernizationResult(
            boolean modified,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> blockingObligations
    ) {}

    private static final Pattern CLASSIC_DEPENDENCY = Pattern.compile(
            "(?s)<dependency>\\s*<groupId>(?:org\\.springframework\\.boot|org\\.apache\\.activemq)</groupId>\\s*"
                    + "<artifactId>(?:spring-boot-starter-activemq|activemq-client|activemq-spring)</artifactId>"
                    + "(?:(?!</dependency>).)*?</dependency>");
    private static final String ARTEMIS_DEPENDENCY = """
            <dependency>
              <groupId>org.springframework.boot</groupId>
              <artifactId>spring-boot-starter-artemis</artifactId>
            </dependency>""";

    private SpringActiveMqToArtemisModernizer() {}

    public static ModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        Set<String> changed = new LinkedHashSet<>();
        List<String> rules = new ArrayList<>();
        List<String> blockers = new ArrayList<>();
        if (!Files.isDirectory(projectRoot)) {
            return new ModernizationResult(false, changed, rules, List.of("project root does not exist"));
        }
        try (var files = Files.walk(projectRoot)) {
            for (Path file : files.filter(Files::isRegularFile).toList()) {
                String name = file.getFileName().toString();
                if (name.equals("pom.xml")) rewritePom(projectRoot, file, changed, rules);
                else if (name.endsWith(".java")) rewriteJava(projectRoot, file, changed, rules, blockers);
                else if (name.startsWith("application.") || name.startsWith("bootstrap.")) {
                    rewriteConfig(projectRoot, file, changed, rules);
                } else if (name.endsWith(".xml")) inspectBrokerXml(projectRoot, file, blockers);
            }
        } catch (IOException e) {
            blockers.add("IO:" + e.getClass().getSimpleName());
        }
        return new ModernizationResult(!changed.isEmpty(), Set.copyOf(changed),
                List.copyOf(rules), List.copyOf(blockers));
    }

    private static void rewritePom(Path root, Path file, Set<String> changed, List<String> rules)
            throws IOException {
        String before = Files.readString(file, StandardCharsets.UTF_8);
        Matcher matcher = CLASSIC_DEPENDENCY.matcher(before);
        if (!matcher.find()) return;
        StringBuffer output = new StringBuffer();
        boolean first = true;
        do {
            matcher.appendReplacement(output, first ? Matcher.quoteReplacement(ARTEMIS_DEPENDENCY) : "");
            first = false;
        } while (matcher.find());
        matcher.appendTail(output);
        String after = output.toString();
        Files.writeString(file, after, StandardCharsets.UTF_8);
        changed.add(relative(root, file));
        rules.add("ACTIVEMQ_CLASSIC_TO_BOOT_ARTEMIS_STARTER");
    }

    private static void rewriteJava(
            Path root, Path file, Set<String> changed, List<String> rules, List<String> blockers
    ) throws IOException {
        String before = Files.readString(file, StandardCharsets.UTF_8);
        if (!before.contains("javax.jms") && !before.contains("org.apache.activemq.ActiveMQConnectionFactory")) return;
        if (before.contains("ActiveMQPrefetchPolicy") || before.contains("RedeliveryPolicy")
                || before.contains("ActiveMQAdvisoryConsumer") || before.contains("VirtualTopic")) {
            blockers.add(relative(root, file)
                    + ": Classic-specific prefetch/redelivery/advisory/virtual-topic behavior needs an Artemis address contract");
            return;
        }
        String after = before
                .replace("javax.jms.", "jakarta.jms.")
                .replace("import org.apache.activemq.ActiveMQConnectionFactory;",
                        "import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;");
        if (!after.equals(before)) {
            Files.writeString(file, after, StandardCharsets.UTF_8);
            changed.add(relative(root, file));
            rules.add("JAKARTA_JMS_AND_ARTEMIS_CONNECTION_FACTORY");
        }
    }

    private static void rewriteConfig(Path root, Path file, Set<String> changed, List<String> rules)
            throws IOException {
        String before = Files.readString(file, StandardCharsets.UTF_8);
        if (!before.contains("spring.activemq") && !before.contains("activemq:")) return;
        String after = before.replace("spring.activemq.", "spring.artemis.")
                .replace("  activemq:", "  artemis:");
        if (!after.equals(before)) {
            Files.writeString(file, after, StandardCharsets.UTF_8);
            changed.add(relative(root, file));
            rules.add("SPRING_ACTIVEMQ_PROPERTIES_TO_ARTEMIS");
        }
    }

    private static void inspectBrokerXml(Path root, Path file, List<String> blockers) throws IOException {
        String content = Files.readString(file, StandardCharsets.UTF_8);
        if (content.contains("http://activemq.apache.org/schema/core")
                || content.contains("<amq:broker") || content.contains("<broker")) {
            blockers.add(relative(root, file)
                    + ": broker topology, persistence, destination policy, and dead-letter semantics require replay on a real Artemis broker");
        }
    }

    private static String relative(Path root, Path file) {
        return root.relativize(file).toString().replace('\\', '/');
    }
}
