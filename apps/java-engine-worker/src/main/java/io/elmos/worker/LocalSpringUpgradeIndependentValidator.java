package io.elmos.worker;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.zip.ZipInputStream;

import static io.elmos.worker.SpringUpgradeModels.*;

/**
 * A verification-role component. It consumes only the content-addressed downloadable artifact,
 * expands it into a fresh directory, verifies the exact target tuple and executes Maven verify.
 * It does not invoke OpenRewrite and cannot modify the candidate artifact. Deployment evidence
 * must state whether this role is hosted by a physically separate verifier service.
 */
final class LocalSpringUpgradeIndependentValidator implements SpringUpgradeIndependentValidationPort {
    private static final int MAX_ENTRIES = 100_000;
    private static final long MAX_BYTES = 512L * 1024 * 1024;
    private final Path workspaceRoot;
    private final Path javaHome;
    private final String mavenExecutable;
    private final ObjectMapper json;
    private final String verifierId;

    LocalSpringUpgradeIndependentValidator(
            Path workspaceRoot,
            Path javaHome,
            String mavenExecutable,
            ObjectMapper json,
            String verifierId
    ) {
        this.workspaceRoot = Objects.requireNonNull(workspaceRoot).toAbsolutePath().normalize();
        this.javaHome = Objects.requireNonNull(javaHome).toAbsolutePath().normalize();
        this.mavenExecutable = requireMaven(mavenExecutable, this.javaHome);
        this.json = Objects.requireNonNull(json);
        this.verifierId = Objects.requireNonNull(verifierId);
        if (!Files.isExecutable(this.javaHome.resolve("bin/java"))) {
            throw new IllegalStateException("independent validator Java 21 is unavailable");
        }
    }

    @Override
    public IndependentValidationResult validate(
            ExecutionResult result,
            Path rawRunRoot,
            SpringUpgradeExecutionPort.Control control
    ) {
        Path runRoot = confined(rawRunRoot);
        control.stage(Stage.INDEPENDENT_VALIDATION,
                "Independent verifier is validating the immutable download artifact in a fresh workspace");
        if (!result.artifactSha256().equals(sha256(result.downloadArtifact()))) {
            throw blocked("ARTIFACT_DIGEST_MISMATCH",
                    "Candidate artifact bytes differ from the transformation result digest.");
        }
        Path validationRoot = runRoot.resolve("independent-validation");
        deleteTree(validationRoot);
        unzip(result.downloadArtifact(), validationRoot);
        TargetTuple target = targetTuple(result, runRoot);
        validateTargetTuple(validationRoot, target);
        runVerify(validationRoot, control);
        Instant decidedAt = Instant.now();
        Path evidence = runRoot.resolve("evidence/independent-validation.json");
        Map<String, Object> record = new LinkedHashMap<>();
        record.put("schema_version", "1.0");
        record.put("verifier_id", verifierId);
        record.put("producer_role", "TRANSFORMER");
        record.put("verifier_role", "INDEPENDENT_VALIDATOR");
        record.put("fresh_artifact_workspace", true);
        record.put("transform_capability", "NONE");
        record.put("physically_separate_verifier_service", false);
        record.put("artifact_sha256", result.artifactSha256());
        record.put("target_spring_boot", target.springBoot());
        record.put("target_java", target.java());
        record.put("command", List.of(mavenExecutable, "-B", "--no-transfer-progress", "verify"));
        record.put("status", "PASS");
        record.put("decided_at", decidedAt);
        writeJson(evidence, record);
        return new IndependentValidationResult(
                "PASS",
                verifierId,
                result.artifactSha256(),
                runRoot.relativize(evidence).toString(),
                decidedAt
        );
    }

    @Override public boolean configured() { return true; }
    @Override public String configurationReason() {
        return "Fresh-artifact Maven verifier role is configured; deployment evidence must independently prove process and authority separation.";
    }

    private static String requireMaven(String command, Path javaHome) {
        if (command == null || command.isBlank() || command.indexOf('\0') >= 0) {
            throw new IllegalArgumentException("Maven executable is required");
        }
        ProcessBuilder builder = new ProcessBuilder(command, "-version").redirectErrorStream(true);
        builder.environment().put("JAVA_HOME", javaHome.toString());
        try {
            Process process = builder.start();
            String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            if (!process.waitFor(15, TimeUnit.SECONDS) || process.exitValue() != 0
                    || !output.contains("Apache Maven 3.9.11")) {
                process.destroyForcibly();
                throw new IllegalStateException("approved verifier Maven executable must be exactly 3.9.11");
            }
            return command;
        } catch (IOException | InterruptedException error) {
            if (error instanceof InterruptedException) Thread.currentThread().interrupt();
            throw new IllegalStateException("approved verifier Maven executable could not be verified", error);
        }
    }

    private void runVerify(Path root, SpringUpgradeExecutionPort.Control control) {
        List<String> command = List.of(
                mavenExecutable,
                "-B",
                "--no-transfer-progress",
                "verify"
        );
        ProcessBuilder builder = new ProcessBuilder(command)
                .directory(root.toFile())
                .redirectErrorStream(true);
        builder.environment().put("JAVA_HOME", javaHome.toString());
        builder.environment().put("MAVEN_OPTS", "-Djava.awt.headless=true -Duser.timezone=UTC");
        try {
            Process process = builder.start();
            control.process(process);
            Thread output = Thread.ofVirtual().start(() -> {
                try (var reader = process.inputReader(StandardCharsets.UTF_8)) {
                    reader.lines().forEach(control::log);
                } catch (IOException error) {
                    control.log("independent validation output collection failed");
                }
            });
            boolean completed = process.waitFor(Duration.ofMinutes(30).toMillis(), TimeUnit.MILLISECONDS);
            if (!completed) {
                process.destroyForcibly();
                output.join(5_000);
                throw blocked("INDEPENDENT_VALIDATION_TIMEOUT",
                        "Independent Maven verification exceeded its execution budget.");
            }
            output.join(5_000);
            if (process.exitValue() != 0) {
                throw blocked("INDEPENDENT_VALIDATION_FAILED",
                        "Independent Maven verification failed; the artifact remains unavailable.");
            }
        } catch (BlockedException error) {
            throw error;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw blocked("INDEPENDENT_VALIDATION_INTERRUPTED",
                    "Independent validation was interrupted.");
        } catch (IOException error) {
            throw blocked("INDEPENDENT_VALIDATOR_UNAVAILABLE",
                    "Independent validation toolchain could not be started.");
        }
    }

    private static void unzip(Path artifact, Path target) {
        try {
            Files.createDirectories(target);
            int entries = 0;
            long total = 0;
            try (ZipInputStream input = new ZipInputStream(Files.newInputStream(artifact))) {
                java.util.zip.ZipEntry entry;
                byte[] buffer = new byte[64 * 1024];
                while ((entry = input.getNextEntry()) != null) {
                    if (++entries > MAX_ENTRIES) throw new SecurityException("artifact entry limit exceeded");
                    Path destination = target.resolve(entry.getName()).normalize();
                    if (!destination.startsWith(target) || entry.getName().startsWith("/")) {
                        throw new SecurityException("artifact entry escapes validation workspace");
                    }
                    if (entry.isDirectory()) {
                        Files.createDirectories(destination);
                    } else {
                        Files.createDirectories(destination.getParent());
                        try (var output = Files.newOutputStream(destination, StandardOpenOption.CREATE_NEW)) {
                            int count;
                            while ((count = input.read(buffer)) >= 0) {
                                total = Math.addExact(total, count);
                                if (total > MAX_BYTES) throw new SecurityException("artifact byte limit exceeded");
                                output.write(buffer, 0, count);
                            }
                        }
                    }
                    input.closeEntry();
                }
            }
        } catch (IOException | RuntimeException error) {
            deleteTree(target);
            if (error instanceof BlockedException blocked) throw blocked;
            throw blocked("ARTIFACT_EXTRACTION_REJECTED",
                    "Candidate artifact could not be safely expanded for independent validation.");
        }
    }

    private TargetTuple targetTuple(ExecutionResult result, Path runRoot) {
        try {
            Path fcm = runRoot.resolve(result.fcmArtifact()).normalize();
            if (!fcm.startsWith(runRoot)
                    || !Files.isRegularFile(fcm, LinkOption.NOFOLLOW_LINKS)
                    || Files.isSymbolicLink(fcm)) {
                throw blocked("FCM_TARGET_TUPLE_UNAVAILABLE",
                        "Authoritative Framework Contract Model is unavailable to the verifier.");
            }
            var tuple = json.readTree(fcm.toFile()).path("exact_tuple");
            String boot = tuple.path("targetSpringBoot").asText("");
            String java = tuple.path("targetJava").asText("");
            if (!supportedTarget(boot, java)) {
                throw blocked("FCM_TARGET_TUPLE_UNSUPPORTED",
                        "Framework Contract Model requested a target outside the verifier allowlist.");
            }
            return new TargetTuple(boot, java);
        } catch (BlockedException error) {
            throw error;
        } catch (IOException error) {
            throw blocked("FCM_TARGET_TUPLE_UNAVAILABLE",
                    "Authoritative Framework Contract Model could not be read by the verifier.");
        }
    }

    private static boolean supportedTarget(String boot, String java) {
        return ("2.7.18".equals(boot) && "17".equals(java))
                || ("3.2.12".equals(boot) && "17".equals(java))
                || ("3.5.3".equals(boot) && "21".equals(java));
    }

    private static void validateTargetTuple(Path root, TargetTuple expected) {
        Path pom = root.resolve("pom.xml");
        if (!Files.isRegularFile(pom, LinkOption.NOFOLLOW_LINKS)) {
            throw blocked("TARGET_POM_MISSING", "Candidate artifact has no root Maven project.");
        }
        Document document = parsePom(pom);
        String boot = springBootVersion(document);
        String java = property(document, "java.version");
        if (java.isBlank()) java = property(document, "maven.compiler.release");
        if (!expected.springBoot().equals(boot) || !expected.java().equals(java)) {
            throw blocked("TARGET_TUPLE_MISMATCH",
                    "Candidate artifact does not match the FCM target Spring Boot / Java tuple.");
        }
    }

    private record TargetTuple(String springBoot, String java) {}

    private static Document parsePom(Path pom) {
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            return factory.newDocumentBuilder().parse(pom.toFile());
        } catch (Exception error) {
            throw blocked("TARGET_POM_INVALID", "Candidate Maven project model is invalid.");
        }
    }

    private static String springBootVersion(Document document) {
        Element root = document.getDocumentElement();
        Element parent = direct(root, "parent");
        if (parent != null && "spring-boot-starter-parent".equals(text(parent, "artifactId"))) {
            return resolveProperty(document, text(parent, "version"));
        }
        for (Element dependency : descendants(root, "dependency")) {
            if ("org.springframework.boot".equals(text(dependency, "groupId"))
                    && "spring-boot-dependencies".equals(text(dependency, "artifactId"))) {
                return resolveProperty(document, text(dependency, "version"));
            }
        }
        return resolveProperty(document, property(document, "spring-boot.version"));
    }

    private static String property(Document document, String name) {
        Element properties = direct(document.getDocumentElement(), "properties");
        if (properties == null) return "";
        for (Element element : directChildren(properties, name)) {
            return element.getTextContent().trim();
        }
        return "";
    }

    private static String resolveProperty(Document document, String value) {
        String trimmed = Objects.toString(value, "").trim();
        if (trimmed.matches("\\$\\{[^}]+}")) {
            return property(document, trimmed.substring(2, trimmed.length() - 1));
        }
        return trimmed;
    }

    private static Element direct(Element parent, String name) {
        return directChildren(parent, name).stream().findFirst().orElse(null);
    }

    private static List<Element> directChildren(Element parent, String name) {
        List<Element> result = new ArrayList<>();
        NodeList nodes = parent.getChildNodes();
        for (int i = 0; i < nodes.getLength(); i++) {
            Node child = nodes.item(i);
            if (child instanceof Element element
                    && (element.getLocalName() == null ? element.getTagName() : element.getLocalName()).equals(name)) {
                result.add(element);
            }
        }
        return result;
    }

    private static List<Element> descendants(Element root, String name) {
        List<Element> result = new ArrayList<>();
        NodeList nodes = root.getElementsByTagNameNS("*", name);
        for (int i = 0; i < nodes.getLength(); i++) {
            if (nodes.item(i) instanceof Element element) result.add(element);
        }
        return result;
    }

    private static String text(Element parent, String child) {
        Element value = direct(parent, child);
        return value == null ? "" : value.getTextContent().trim();
    }

    private Path confined(Path raw) {
        Path path = raw.toAbsolutePath().normalize();
        if (!path.startsWith(workspaceRoot) || path.equals(workspaceRoot)) {
            throw blocked("WORKSPACE_PATH_REJECTED",
                    "Independent validation path must remain below the configured workspace root.");
        }
        return path;
    }

    private void writeJson(Path path, Object value) {
        try {
            Files.createDirectories(path.getParent());
            json.writerWithDefaultPrettyPrinter().writeValue(path.toFile(), value);
        } catch (IOException error) {
            throw blocked("VALIDATION_EVIDENCE_WRITE_FAILED",
                    "Independent validation evidence could not be written.");
        }
    }

    private static String sha256(Path path) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (var input = Files.newInputStream(path)) {
                byte[] buffer = new byte[64 * 1024];
                int count;
                while ((count = input.read(buffer)) >= 0) digest.update(buffer, 0, count);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (Exception error) {
            throw blocked("ARTIFACT_DIGEST_UNAVAILABLE", "Candidate artifact digest could not be calculated.");
        }
    }

    private static void deleteTree(Path target) {
        if (target == null || !Files.exists(target, LinkOption.NOFOLLOW_LINKS)) return;
        try {
            Files.walkFileTree(target, new SimpleFileVisitor<>() {
                @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) throws IOException {
                    Files.deleteIfExists(file);
                    return FileVisitResult.CONTINUE;
                }

                @Override public FileVisitResult postVisitDirectory(Path dir, IOException error) throws IOException {
                    if (error != null) throw error;
                    Files.deleteIfExists(dir);
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException error) {
            throw new IllegalStateException("independent validation workspace cleanup failed", error);
        }
    }

    private static BlockedException blocked(String code, String message) {
        return new BlockedException(code, message);
    }
}
