package io.elmos.verifier;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.util.*;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipFile;

import static io.elmos.verifier.VerificationModels.*;

final class SpringArtifactVerifier {
    private static final int MAX_ENTRIES = 100_000;
    private static final long MAX_EXPANDED_BYTES = 512L * 1024 * 1024;
    private static final long MAX_ARTIFACT_BYTES = 256L * 1024 * 1024;

    private final String verifierId;
    private final Path inputRoot;
    private final Path evidenceRoot;
    private final VerifierAuthentication authentication;
    private final Map<String, MavenVerification> mavenByTargetJava;
    private final ObjectMapper json;
    private final Clock clock;

    SpringArtifactVerifier(
            String verifierId,
            Path inputRoot,
            Path evidenceRoot,
            VerifierAuthentication authentication,
            MavenVerification maven,
            ObjectMapper json,
            Clock clock
    ) {
        this(verifierId, inputRoot, evidenceRoot, authentication,
                Map.of("21", maven), json, clock);
    }

    SpringArtifactVerifier(
            String verifierId,
            Path inputRoot,
            Path evidenceRoot,
            VerifierAuthentication authentication,
            Map<String, MavenVerification> mavenByTargetJava,
            ObjectMapper json,
            Clock clock
    ) {
        this.verifierId = requireIdentifier(verifierId, "verifier ID");
        this.inputRoot = inputRoot.toAbsolutePath().normalize();
        this.evidenceRoot = evidenceRoot.toAbsolutePath().normalize();
        this.authentication = Objects.requireNonNull(authentication);
        this.mavenByTargetJava = Map.copyOf(Objects.requireNonNull(mavenByTargetJava));
        if (this.mavenByTargetJava.isEmpty()) {
            throw new IllegalArgumentException("at least one exact target JDK verifier is required");
        }
        this.json = Objects.requireNonNull(json);
        this.clock = Objects.requireNonNull(clock);
        if (this.inputRoot.equals(this.evidenceRoot)
                || this.inputRoot.startsWith(this.evidenceRoot)
                || this.evidenceRoot.startsWith(this.inputRoot)) {
            throw new IllegalArgumentException("verifier input and evidence roots must be separate");
        }
        try {
            Files.createDirectories(this.evidenceRoot);
        } catch (IOException error) {
            throw new IllegalStateException("verifier evidence root is unavailable", error);
        }
    }

    Response verify(String timestamp, String nonce, String signature, byte[] body) {
        authentication.verify(timestamp, nonce, signature, body);
        Request request = parse(body);
        validateRequest(request);
        Path artifact = artifact(request.artifactRelativePath());
        if (!request.artifactSha256().equals(sha256(artifact))) {
            throw rejected("ARTIFACT_DIGEST_MISMATCH",
                    "Candidate artifact bytes differ from the transformation digest.");
        }

        Path decisionRoot = evidenceRoot.resolve(request.runId())
                .resolve(request.artifactSha256().substring(0, 16))
                .normalize();
        if (!decisionRoot.startsWith(evidenceRoot)) {
            throw rejected("EVIDENCE_PATH_REJECTED", "Verifier evidence path is invalid.");
        }
        Path storedResponse = decisionRoot.resolve("response.json");
        if (Files.isRegularFile(storedResponse, LinkOption.NOFOLLOW_LINKS)) {
            return readResponse(storedResponse, request);
        }

        Path candidate = decisionRoot.resolve("candidate");
        Path log = decisionRoot.resolve("maven-verify.log");
        Path decision = decisionRoot.resolve("decision.json");
        Path runtimeArtifact = decisionRoot.resolve("verified-application.jar");
        try {
            Files.createDirectories(decisionRoot);
            deleteTree(candidate);
            Files.deleteIfExists(log);
            Files.deleteIfExists(runtimeArtifact);
            unzip(artifact, candidate);
            validateTargetTuple(candidate, request.targetSpringBoot(), request.targetJava());
            MavenVerification maven = mavenByTargetJava.get(request.targetJava());
            if (maven == null) {
                throw rejected("TARGET_JDK_NOT_PROVISIONED",
                        "Independent verifier does not provide the exact requested target JDK.");
            }
            List<String> command = maven.verify(candidate, log);
            Files.copy(bootJar(candidate), runtimeArtifact);
            Instant decidedAt = clock.instant();
            Map<String, Object> record = new LinkedHashMap<>();
            record.put("schema_version", "1.0");
            record.put("run_id", request.runId());
            record.put("verifier_id", verifierId);
            record.put("producer_role", "TRANSFORMER");
            record.put("verifier_role", "INDEPENDENT_VALIDATOR");
            record.put("fresh_artifact_workspace", true);
            record.put("transform_capability", false);
            record.put("physically_separate_verifier_service", true);
            record.put("input_mount_mode", "READ_ONLY");
            record.put("artifact_sha256", request.artifactSha256());
            record.put("target_spring_boot", request.targetSpringBoot());
            record.put("target_java", request.targetJava());
            record.put("command", command);
            record.put("runtime_artifact_relative_path", evidenceRoot.relativize(runtimeArtifact).toString());
            record.put("runtime_artifact_sha256", sha256(runtimeArtifact));
            record.put("runtime_artifact_bytes", Files.size(runtimeArtifact));
            record.put("status", "PASS");
            record.put("decided_at", decidedAt);
            atomicJson(decision, record);
            Response response = new Response(
                    "PASS",
                    verifierId,
                    request.artifactSha256(),
                    request.targetSpringBoot(),
                    request.targetJava(),
                    true,
                    false,
                    true,
                    evidenceRoot.relativize(decision).toString(),
                    evidenceRoot.relativize(log).toString(),
                    sha256(decision),
                    Files.size(decision),
                    sha256(log),
                    Files.size(log),
                    evidenceRoot.relativize(runtimeArtifact).toString(),
                    sha256(runtimeArtifact),
                    Files.size(runtimeArtifact),
                    command,
                    decidedAt
            );
            atomicJson(storedResponse, response);
            return response;
        } catch (Rejected error) {
            throw error;
        } catch (IOException error) {
            throw rejected("VERIFICATION_EVIDENCE_WRITE_FAILED",
                    "Independent verifier evidence could not be persisted.");
        } finally {
            deleteTree(candidate);
        }
    }

    private Request parse(byte[] body) {
        try {
            if (body.length == 0 || body.length > 64 * 1024) {
                throw rejected("REQUEST_REJECTED", "Verifier request body is invalid.");
            }
            return json.readValue(body, Request.class);
        } catch (Rejected error) {
            throw error;
        } catch (IOException error) {
            throw rejected("REQUEST_REJECTED", "Verifier request body is invalid.");
        }
    }

    private static void validateRequest(Request request) {
        if (request == null
                || request.runId() == null
                || !request.runId().matches("[0-9a-fA-F-]{36}")
                || request.artifactRelativePath() == null
                || request.artifactRelativePath().isBlank()
                || request.artifactSha256() == null
                || !request.artifactSha256().matches("[0-9a-f]{64}")
                || !supportedTarget(request.targetSpringBoot(), request.targetJava())) {
            throw rejected("REQUEST_REJECTED", "Verifier request fields are invalid.");
        }
        try {
            UUID.fromString(request.runId());
        } catch (IllegalArgumentException error) {
            throw rejected("REQUEST_REJECTED", "Verifier run ID is invalid.");
        }
    }

    private Path artifact(String relativeValue) {
        Path relative;
        try {
            relative = Path.of(relativeValue);
        } catch (InvalidPathException error) {
            throw rejected("ARTIFACT_PATH_REJECTED", "Candidate artifact path is invalid.");
        }
        if (relative.isAbsolute() || relative.normalize().startsWith("..")) {
            throw rejected("ARTIFACT_PATH_REJECTED", "Candidate artifact path escapes the input root.");
        }
        Path candidate = inputRoot.resolve(relative).normalize();
        if (!candidate.startsWith(inputRoot)
                || !Files.isRegularFile(candidate, LinkOption.NOFOLLOW_LINKS)
                || Files.isSymbolicLink(candidate)) {
            throw rejected("ARTIFACT_UNAVAILABLE", "Candidate artifact is unavailable to the verifier.");
        }
        Path cursor = inputRoot;
        for (Path segment : inputRoot.relativize(candidate)) {
            cursor = cursor.resolve(segment);
            if (Files.isSymbolicLink(cursor)) {
                throw rejected("ARTIFACT_PATH_REJECTED", "Candidate artifact path contains a symbolic link.");
            }
        }
        try {
            long size = Files.size(candidate);
            if (size <= 0 || size > MAX_ARTIFACT_BYTES) {
                throw rejected("ARTIFACT_SIZE_REJECTED", "Candidate artifact size is outside policy.");
            }
        } catch (IOException error) {
            throw rejected("ARTIFACT_UNAVAILABLE", "Candidate artifact metadata is unavailable.");
        }
        return candidate;
    }

    private Response readResponse(Path responseFile, Request request) {
        try {
            Response response = json.readValue(responseFile.toFile(), Response.class);
            if (!"PASS".equals(response.status())
                    || !verifierId.equals(response.verifierId())
                    || !request.artifactSha256().equals(response.artifactSha256())
                    || !request.targetSpringBoot().equals(response.targetSpringBoot())
                    || !request.targetJava().equals(response.targetJava())
                    || !response.physicallySeparateVerifierService()
                    || response.transformCapability()) {
                throw rejected("STALE_VERIFIER_RECEIPT", "Stored verifier receipt does not match this request.");
            }
            Path decision = evidenceRoot.resolve(response.evidenceRelativePath()).normalize();
            Path log = evidenceRoot.resolve(response.logRelativePath()).normalize();
            if (!decision.startsWith(evidenceRoot)
                    || !log.startsWith(evidenceRoot)
                    || !response.evidenceSha256().equals(sha256(decision))
                    || !response.logSha256().equals(sha256(log))
                    || response.evidenceBytes() != Files.size(decision)
                    || response.logBytes() != Files.size(log)) {
                throw rejected("VERIFIER_EVIDENCE_DIGEST_MISMATCH",
                        "Stored verifier evidence differs from its receipt.");
            }
            Path runtimeArtifact = evidenceRoot.resolve(response.runtimeArtifactRelativePath()).normalize();
            if (!runtimeArtifact.startsWith(evidenceRoot)
                    || !response.runtimeArtifactSha256().equals(sha256(runtimeArtifact))
                    || response.runtimeArtifactBytes() != Files.size(runtimeArtifact)) {
                throw rejected("VERIFIER_RUNTIME_ARTIFACT_DIGEST_MISMATCH",
                        "Stored verified runtime Artifact differs from its receipt.");
            }
            return response;
        } catch (Rejected error) {
            throw error;
        } catch (IOException error) {
            throw rejected("STALE_VERIFIER_RECEIPT", "Stored verifier receipt could not be read.");
        }
    }

    private void atomicJson(Path path, Object value) throws IOException {
        Files.createDirectories(path.getParent());
        Path temporary = Files.createTempFile(path.getParent(), path.getFileName().toString(), ".tmp");
        try {
            json.writerWithDefaultPrettyPrinter().writeValue(temporary.toFile(), value);
            try {
                Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException error) {
                Files.move(temporary, path);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private static void unzip(Path artifact, Path target) {
        try {
            Files.createDirectories(target);
            int entries = 0;
            long total = 0;
            try (ZipInputStream input = new ZipInputStream(Files.newInputStream(artifact))) {
                ZipEntry entry;
                byte[] buffer = new byte[64 * 1024];
                while ((entry = input.getNextEntry()) != null) {
                    if (++entries > MAX_ENTRIES) throw new SecurityException("artifact entry limit exceeded");
                    if (entry.getName().contains("\0") || entry.getName().startsWith("/")) {
                        throw new SecurityException("artifact entry is invalid");
                    }
                    Path destination = target.resolve(entry.getName()).normalize();
                    if (!destination.startsWith(target)) {
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
                                if (total > MAX_EXPANDED_BYTES) throw new SecurityException("artifact byte limit exceeded");
                                output.write(buffer, 0, count);
                            }
                        }
                    }
                    input.closeEntry();
                }
            }
        } catch (IOException | RuntimeException error) {
            deleteTree(target);
            throw rejected("ARTIFACT_EXTRACTION_REJECTED",
                    "Candidate artifact could not be safely expanded.");
        }
    }

    private static boolean supportedTarget(String boot, String java) {
        return ("2.7.18".equals(boot) && "17".equals(java))
                || ("3.2.12".equals(boot) && "17".equals(java))
                || ("3.5.3".equals(boot) && "21".equals(java));
    }

    private static void validateTargetTuple(Path root, String expectedBoot, String expectedJava) {
        Path pom = root.resolve("pom.xml");
        if (!Files.isRegularFile(pom, LinkOption.NOFOLLOW_LINKS)) {
            throw rejected("TARGET_POM_MISSING", "Candidate artifact has no root Maven project.");
        }
        Document document = parsePom(pom);
        String boot = springBootVersion(document);
        String java = property(document, "java.version");
        if (java.isBlank()) java = property(document, "maven.compiler.release");
        if (!expectedBoot.equals(boot) || !expectedJava.equals(java)) {
            throw rejected("TARGET_TUPLE_MISMATCH",
                    "Candidate artifact does not match the requested exact Spring Boot / Java tuple.");
        }
    }

    private static Path bootJar(Path root) {
        Path target = root.resolve("target");
        try (var stream = Files.list(target)) {
            return stream.filter(path -> path.getFileName().toString().endsWith(".jar"))
                    .filter(path -> !path.getFileName().toString().endsWith(".original"))
                    .filter(SpringArtifactVerifier::isBootJar)
                    .sorted()
                    .findFirst()
                    .orElseThrow(() -> rejected(
                            "VERIFIED_BOOT_JAR_NOT_FOUND",
                            "Independent Maven verification did not produce an executable Boot JAR."));
        } catch (IOException error) {
            throw rejected("VERIFIED_BOOT_JAR_NOT_FOUND",
                    "Independent Maven verification did not produce an executable Boot JAR.");
        }
    }

    private static boolean isBootJar(Path path) {
        try (ZipFile archive = new ZipFile(path.toFile())) {
            return archive.getEntry("BOOT-INF/classes/") != null
                    && archive.getEntry("META-INF/MANIFEST.MF") != null;
        } catch (IOException error) {
            return false;
        }
    }

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
            throw rejected("TARGET_POM_INVALID", "Candidate Maven project model is invalid.");
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
        for (Element element : directChildren(properties, name)) return element.getTextContent().trim();
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
        for (int index = 0; index < nodes.getLength(); index++) {
            Node child = nodes.item(index);
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
        for (int index = 0; index < nodes.getLength(); index++) {
            if (nodes.item(index) instanceof Element element) result.add(element);
        }
        return result;
    }

    private static String text(Element parent, String child) {
        Element value = direct(parent, child);
        return value == null ? "" : value.getTextContent().trim();
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
            throw rejected("EVIDENCE_DIGEST_UNAVAILABLE", "Verifier evidence digest could not be calculated.");
        }
    }

    private static String requireIdentifier(String value, String label) {
        if (value == null || !value.matches("[a-zA-Z0-9._-]{3,96}")) {
            throw new IllegalArgumentException(label + " is invalid");
        }
        return value;
    }

    private static void deleteTree(Path target) {
        if (target == null || !Files.exists(target, LinkOption.NOFOLLOW_LINKS)) return;
        try {
            Files.walkFileTree(target, new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) throws IOException {
                    Files.deleteIfExists(file);
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult postVisitDirectory(Path directory, IOException error) throws IOException {
                    if (error != null) throw error;
                    Files.deleteIfExists(directory);
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException error) {
            throw rejected("VERIFIER_WORKSPACE_CLEANUP_FAILED",
                    "Independent verifier workspace cleanup failed.");
        }
    }

    private static Rejected rejected(String code, String message) {
        return new Rejected(code, message);
    }
}
