package io.elmos.worker;

import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Discovers and analyzes Maven multi-module reactor topology and Gradle multi-project structures.
 *
 * <p>Enterprise legacy applications frequently employ aggregator and parent-child POM hierarchies.
 * This scanner discovers all module descriptors so that transformations, dependency injections,
 * and compiler repair cycles can be applied across the entire multi-module project graph.
 */
public final class SpringMultiModuleProjectScanner {

    private static final Pattern MODULE_PATTERN = Pattern.compile("<module>\\s*([^<]+)\\s*</module>");

    private SpringMultiModuleProjectScanner() {}

    /**
     * Discovers all regular {@code pom.xml} files in the given project tree,
     * ignoring version control directories and temporary build directories.
     */
    public static List<Path> findPomFiles(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        if (!Files.isDirectory(projectRoot)) {
            return Collections.emptyList();
        }

        Set<Path> poms = new LinkedHashSet<>();
        Path rootPom = projectRoot.resolve("pom.xml");
        if (Files.isRegularFile(rootPom)) {
            poms.add(rootPom.toAbsolutePath().normalize());
        }

        try {
            Files.walkFileTree(projectRoot, new SimpleFileVisitor<>() {
                @Override
                public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs) {
                    String name = dir.getFileName().toString();
                    if (name.equals(".git") || name.equals("target") || name.equals(".idea") || name.equals("build")) {
                        return FileVisitResult.SKIP_SUBTREE;
                    }
                    return FileVisitResult.CONTINUE;
                }

                @Override
                public FileVisitResult visitFile(Path file, BasicFileAttributes attrs) {
                    if (file.getFileName().toString().equals("pom.xml")) {
                        poms.add(file.toAbsolutePath().normalize());
                    }
                    return FileVisitResult.CONTINUE;
                }
            });
        } catch (IOException ignored) {}

        List<Path> result = new ArrayList<>(poms);
        Collections.sort(result);
        return Collections.unmodifiableList(result);
    }

    /**
     * Reads module names declared in a Maven aggregator {@code pom.xml}.
     */
    public static List<String> declaredSubmodules(Path pomFile) {
        if (!Files.isRegularFile(pomFile)) {
            return Collections.emptyList();
        }
        try {
            String text = Files.readString(pomFile);
            List<String> modules = new ArrayList<>();
            Matcher matcher = MODULE_PATTERN.matcher(text);
            while (matcher.find()) {
                String module = matcher.group(1).trim();
                if (!module.isEmpty()) {
                    modules.add(module);
                }
            }
            return Collections.unmodifiableList(modules);
        } catch (IOException e) {
            return Collections.emptyList();
        }
    }

    /**
     * Represents a module within a Maven multi-module reactor.
     */
    public record ReactorModuleNode(
            String artifactId,
            Path pomPath,
            Path moduleDir,
            List<String> submodules,
            int depth
    ) {}

    private static final Pattern ARTIFACT_ID_PATTERN = Pattern.compile(
            "<artifactId>\\s*([^<]+)\\s*</artifactId>"
    );

    /**
     * Resolves the topological DAG execution order for a multi-module reactor.
     */
    public static List<ReactorModuleNode> resolveReactorDag(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        Path rootPom = projectRoot.resolve("pom.xml");
        if (!Files.isRegularFile(rootPom)) {
            return Collections.emptyList();
        }

        List<ReactorModuleNode> nodes = new ArrayList<>();
        Set<Path> visitedPoms = new LinkedHashSet<>();
        traverseModules(rootPom, 0, nodes, visitedPoms);
        return Collections.unmodifiableList(nodes);
    }

    private static void traverseModules(Path currentPom, int depth, List<ReactorModuleNode> nodes, Set<Path> visited) {
        Path normPom = currentPom.toAbsolutePath().normalize();
        if (visited.contains(normPom) || !Files.isRegularFile(normPom)) {
            return;
        }
        visited.add(normPom);

        Path moduleDir = normPom.getParent();
        String artifactId = extractArtifactId(normPom);
        List<String> submodules = declaredSubmodules(normPom);

        nodes.add(new ReactorModuleNode(artifactId, normPom, moduleDir, submodules, depth));

        for (String sub : submodules) {
            Path subPom = moduleDir.resolve(sub).resolve("pom.xml");
            if (Files.isRegularFile(subPom)) {
                traverseModules(subPom, depth + 1, nodes, visited);
            }
        }
    }

    /**
     * Extracts artifactId from a pom.xml.
     */
    public static String extractArtifactId(Path pomFile) {
        if (!Files.isRegularFile(pomFile)) {
            return "unknown";
        }
        try {
            String content = Files.readString(pomFile);
            Matcher matcher = ARTIFACT_ID_PATTERN.matcher(content);
            // Skip parent artifactId if present
            if (content.contains("<parent>")) {
                int parentEnd = content.indexOf("</parent>");
                if (parentEnd != -1) {
                    Matcher afterParent = ARTIFACT_ID_PATTERN.matcher(content.substring(parentEnd));
                    if (afterParent.find()) {
                        return afterParent.group(1).trim();
                    }
                }
            }
            if (matcher.find()) {
                return matcher.group(1).trim();
            }
        } catch (IOException ignored) {}
        return pomFile.getParent().getFileName().toString();
    }

    /**
     * Checks whether the given directory represents a Maven multi-module reactor.
     */
    public static boolean isMultiModule(Path projectRoot) {
        Path rootPom = projectRoot.resolve("pom.xml");
        return Files.isRegularFile(rootPom) && !declaredSubmodules(rootPom).isEmpty();
    }
}
