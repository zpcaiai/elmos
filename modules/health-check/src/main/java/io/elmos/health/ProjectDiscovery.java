package io.elmos.health;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class ProjectDiscovery {
    private static final Set<String> EXCLUDED = Set.of(".git", ".gradle", ".idea", "target", "build", "node_modules", ".next");
    private static final Pattern GRADLE_DEPENDENCY = Pattern.compile("(?m)^[ \\t]*(implementation|api|compileOnly|runtimeOnly|testImplementation)[ \\t]*[('\\\"]+([^:'\\\"]+):([^:'\\\"]+):([^'\\\")]+)");
    private static final Pattern GRADLE_MODULE = Pattern.compile("include[ \\t]*\\(?[ \\t]*['\"]([^'\"]+)['\"]");
    private final ScanPolicy policy;

    ProjectDiscovery(ScanPolicy policy) { this.policy = Objects.requireNonNull(policy); }

    BuildInventory discover(Path requestedRoot) {
        Path root = secureRoot(requestedRoot); List<Path> java = new ArrayList<>(), tests = new ArrayList<>(), builds = new ArrayList<>();
        long[] bytes = {0}; int[] files = {0};
        try {
            Files.walkFileTree(root, new SimpleFileVisitor<>() {
                @Override public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
                    if (!dir.equals(root) && (Files.isSymbolicLink(dir) || EXCLUDED.contains(dir.getFileName().toString()))) return FileVisitResult.SKIP_SUBTREE;
                    return FileVisitResult.CONTINUE;
                }
                @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    if (attrs.isSymbolicLink() || !attrs.isRegularFile()) return FileVisitResult.CONTINUE;
                    files[0]++; bytes[0] += attrs.size();
                    if (files[0] > policy.maxFiles() || bytes[0] > policy.maxTotalBytes()) throw new ScanLimitException();
                    String name = file.getFileName().toString();
                    if (attrs.size() <= policy.maxBytesPerFile()) {
                        if (name.endsWith(".java")) { java.add(file); if (isTest(file)) tests.add(file); }
                        if (name.equals("pom.xml") || name.equals("build.gradle") || name.equals("build.gradle.kts")
                                || name.equals("settings.gradle") || name.equals("settings.gradle.kts") || name.equals("gradle.properties")) builds.add(file);
                    }
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (ScanLimitException error) { throw new IllegalArgumentException("PROJECT_SCAN_LIMIT_EXCEEDED"); }
        catch (IOException error) { throw new IllegalArgumentException("PROJECT_DISCOVERY_FAILED", error); }
        java.sort(Comparator.comparing(Path::toString)); tests.sort(Comparator.comparing(Path::toString)); builds.sort(Comparator.comparing(Path::toString));

        List<HealthModels.Module> modules = new ArrayList<>(); List<HealthModels.Dependency> dependencies = new ArrayList<>();
        List<HealthModels.Finding> findings = new ArrayList<>(); Map<String, String> properties = new HashMap<>();
        boolean hasMaven = false, hasGradle = false, junit = false, coverage = false;
        SecurePomParser parser = new SecurePomParser();
        for (Path build : builds) {
            String name = build.getFileName().toString();
            if (name.equals("pom.xml")) {
                hasMaven = true;
                try {
                    SecurePomParser.PomData data = parser.parse(root, build); modules.add(data.module()); dependencies.addAll(data.dependencies());
                    data.properties().forEach(properties::putIfAbsent); junit |= data.junit(); coverage |= data.coverage();
                    if (data.springBootVersion() != null) properties.putIfAbsent("elmos.spring-boot.version", data.springBootVersion());
                    if (data.springCloudVersion() != null) properties.putIfAbsent("elmos.spring-cloud.version", data.springCloudVersion());
                } catch (IllegalArgumentException error) {
                    findings.add(finding("POM_PARSE_FAILED", "BUILD", HealthModels.Severity.HIGH, normalize(root, build), error.getMessage(), HealthModels.EvidenceStatus.INCONCLUSIVE));
                }
            } else if (name.startsWith("build.gradle")) {
                hasGradle = true; String content = read(build);
                String path = normalize(root, build.getParent());
                String artifact = build.getParent().getFileName() == null ? "root" : build.getParent().getFileName().toString();
                modules.add(new HealthModels.Module(path, null, artifact, gradleValue(content, "version"), HealthModels.BuildSystem.GRADLE, List.of()));
                Matcher matcher = GRADLE_DEPENDENCY.matcher(content);
                while (matcher.find()) dependencies.add(new HealthModels.Dependency(matcher.group(2), matcher.group(3), matcher.group(4).trim(), matcher.group(1), path, true));
                junit |= content.contains("junit") || content.contains("JUnit"); coverage |= content.contains("jacoco");
                putGradleProperty(properties, content, "sourceCompatibility", "maven.compiler.source");
                putGradleProperty(properties, content, "targetCompatibility", "maven.compiler.target");
                Matcher boot = Pattern.compile("org\\.springframework\\.boot[^\\n]*version[ \\t]*['\"]([^'\"]+)").matcher(content);
                if (boot.find()) properties.putIfAbsent("elmos.spring-boot.version", boot.group(1));
            } else if (name.startsWith("settings.gradle")) {
                String content = read(build); Matcher matcher = GRADLE_MODULE.matcher(content); List<String> declared = new ArrayList<>();
                while (matcher.find()) declared.add(matcher.group(1));
                properties.put("elmos.gradle.modules", String.join(",", declared));
            } else if (name.equals("gradle.properties")) {
                for (String line : read(build).lines().toList()) if (!line.isBlank() && !line.stripLeading().startsWith("#") && line.contains("=")) {
                    int separator = line.indexOf('='); properties.putIfAbsent(line.substring(0, separator).trim(), line.substring(separator + 1).trim());
                }
            }
        }
        properties.put("elmos.junit.detected", Boolean.toString(junit)); properties.put("elmos.coverage.detected", Boolean.toString(coverage));
        HealthModels.BuildSystem system = hasMaven && hasGradle ? HealthModels.BuildSystem.MIXED : hasMaven ? HealthModels.BuildSystem.MAVEN
                : hasGradle ? HealthModels.BuildSystem.GRADLE : HealthModels.BuildSystem.UNKNOWN;
        if (system == HealthModels.BuildSystem.UNKNOWN) findings.add(finding("BUILD_SYSTEM_UNKNOWN", "BUILD", HealthModels.Severity.CRITICAL, ".", "No Maven or Gradle build descriptor was found", HealthModels.EvidenceStatus.INCONCLUSIVE));
        List<Path> production = java.stream().filter(path -> !isTest(path)).toList();
        return new BuildInventory(system, modules, dependencies, properties, production, tests, builds, findings);
    }

    private static Path secureRoot(Path requested) {
        Objects.requireNonNull(requested, "project root");
        try {
            Path absolute = requested.toAbsolutePath().normalize();
            if (Files.isSymbolicLink(absolute) || !Files.isDirectory(absolute, LinkOption.NOFOLLOW_LINKS)) throw new SecurityException("project root must be a real directory");
            return absolute.toRealPath(LinkOption.NOFOLLOW_LINKS);
        } catch (IOException error) { throw new IllegalArgumentException("PROJECT_ROOT_UNAVAILABLE", error); }
    }
    static String read(Path file) {
        try { return Files.readString(file, StandardCharsets.UTF_8); }
        catch (IOException error) { throw new IllegalArgumentException("SOURCE_READ_FAILED:" + file.getFileName(), error); }
    }
    private static boolean isTest(Path path) { String value = path.toString().replace('\\', '/'); return value.contains("/src/test/") || value.contains("/src/integrationTest/"); }
    private static String normalize(Path root, Path path) { String value = root.relativize(path).toString().replace('\\', '/'); return value.isBlank() ? "." : value; }
    private static String gradleValue(String content, String key) { Matcher m = Pattern.compile("(?m)^\\s*" + key + "\\s*=\\s*['\"]?([^'\"\\s]+)").matcher(content); return m.find() ? m.group(1) : null; }
    private static void putGradleProperty(Map<String,String> target, String content, String gradleKey, String propertyKey) { String value = gradleValue(content, gradleKey); if (value != null) target.putIfAbsent(propertyKey, value.replace("JavaVersion.VERSION_", "").replace('_', '.')); }
    private static HealthModels.Finding finding(String code, String category, HealthModels.Severity severity, String location, String message, HealthModels.EvidenceStatus status) {
        return new HealthModels.Finding(code, category, severity, location, message, status, Map.of());
    }
    private static final class ScanLimitException extends RuntimeException {}
}
