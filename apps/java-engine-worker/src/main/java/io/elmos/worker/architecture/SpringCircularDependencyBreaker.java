package io.elmos.worker.architecture;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Industrial-grade circular dependency detector and breaker for Spring Boot 2.6+ / 3.x / 4.x.
 *
 * <p>Spring Boot 2.6+ disables circular bean references by default, causing startup aborts with
 * {@code BeanCurrentlyInCreationException}. This modernizer:
 * <ol>
 *   <li>Constructs a bean dependency graph by scanning {@code @Component}, {@code @Service},
 *       {@code @Repository}, and {@code @Configuration} classes for constructor and field injections.</li>
 *   <li>Detects circular dependency cycles using depth-first graph analysis.</li>
 *   <li>Breaks cycles by injecting {@code @Lazy} on constructor parameters or fields within the cycle.</li>
 *   <li>Adds necessary imports for {@code org.springframework.context.annotation.Lazy}.</li>
 * </ol>
 */
public final class SpringCircularDependencyBreaker {

    public record CircularBreakResult(
            boolean modified,
            int changesCount,
            List<String> cyclesBroken,
            Set<String> modifiedFiles
    ) {
        public static CircularBreakResult empty() {
            return new CircularBreakResult(false, 0, Collections.emptyList(), Collections.emptySet());
        }
    }

    private static final Pattern SPRING_BEAN_PATTERN = Pattern.compile(
            "@(Component|Service|Repository|Controller|RestController|Configuration)\\b"
    );

    private static final Pattern CLASS_NAME_PATTERN = Pattern.compile(
            "public\\s+(?:final\\s+)?class\\s+([A-Za-z0-9_]+)"
    );

    private static final Pattern AUTOWIRED_FIELD_PATTERN = Pattern.compile(
            "@(Autowired|Resource|Inject)\\s*(?:private|protected|public)?\\s+(?:final\\s+)?([A-Za-z0-9_]+)\\s+([A-Za-z0-9_]+)\\s*;"
    );

    private SpringCircularDependencyBreaker() {}

    public static CircularBreakResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot cannot be null");
        if (!Files.isDirectory(projectRoot)) {
            return CircularBreakResult.empty();
        }

        Map<String, Path> beanClassFiles = new HashMap<>();
        Map<String, Set<String>> dependencyGraph = new HashMap<>();

        try {
            List<Path> javaFiles;
            try (var stream = Files.walk(projectRoot)) {
                javaFiles = stream
                        .filter(Files::isRegularFile)
                        .filter(p -> p.toString().endsWith(".java"))
                        .toList();
            }

            // 1. Discover all Spring beans and their dependencies
            for (Path javaFile : javaFiles) {
                String content = Files.readString(javaFile, StandardCharsets.UTF_8);
                if (!SPRING_BEAN_PATTERN.matcher(content).find()) {
                    continue;
                }

                Matcher cm = CLASS_NAME_PATTERN.matcher(content);
                if (cm.find()) {
                    String className = cm.group(1);
                    beanClassFiles.put(className, javaFile);

                    Set<String> deps = extractDependencies(className, content);
                    dependencyGraph.put(className, deps);
                }
            }

            // 2. Detect cycles in dependency graph
            List<List<String>> cycles = detectCycles(dependencyGraph);
            if (cycles.isEmpty()) {
                return CircularBreakResult.empty();
            }

            Set<String> modifiedFiles = new LinkedHashSet<>();
            List<String> brokenCycleLogs = new ArrayList<>();
            int changes = 0;

            // 3. Break each cycle by injecting @Lazy on an injection edge
            for (List<String> cycle : cycles) {
                if (cycle.size() < 2) continue;

                // Pick the first edge: source -> target
                String sourceBean = cycle.get(0);
                String targetBean = cycle.get(1);

                Path sourceFile = beanClassFiles.get(sourceBean);
                if (sourceFile != null && Files.exists(sourceFile)) {
                    String original = Files.readString(sourceFile, StandardCharsets.UTF_8);
                    String updated = breakDependencyInContent(original, sourceBean, targetBean);

                    if (!updated.equals(original)) {
                        Files.writeString(sourceFile, updated, StandardCharsets.UTF_8);
                        String rel = projectRoot.relativize(sourceFile).toString().replace("\\", "/");
                        modifiedFiles.add(rel);
                        brokenCycleLogs.add(String.format("BROKE-CYCLE: %s -> %s in %s",
                                String.join(" -> ", cycle), targetBean, sourceBean));
                        changes++;
                    }
                }
            }

            return new CircularBreakResult(
                    changes > 0,
                    changes,
                    Collections.unmodifiableList(brokenCycleLogs),
                    Collections.unmodifiableSet(modifiedFiles)
            );

        } catch (IOException e) {
            return CircularBreakResult.empty();
        }
    }

    public static String breakDependencyInContent(String sourceCode, String sourceBean, String targetBean) {
        String content = sourceCode;

        // If targetBean is already annotated with @Lazy, no-op
        if (content.contains("@Lazy " + targetBean) || content.contains("@Lazy\n    " + targetBean)
                || content.contains("@Lazy\n    private " + targetBean)
                || content.contains("@Lazy\n    @Autowired\n    private " + targetBean)
                || content.contains("@Lazy\n    @Autowired private " + targetBean)) {
            return content;
        }

        boolean modified = false;

        // 1. Constructor parameter injection: public SourceBean(..., TargetBean target, ...)
        Pattern ctorParamPattern = Pattern.compile(
                "(\\b(?:public|protected|private)?\\s*" + Pattern.quote(sourceBean) + "\\s*\\([^)]*?\\b)"
                        + "(?<!@Lazy\\s)" + "(" + Pattern.quote(targetBean) + "\\s+[a-zA-Z0-9_]+)"
        );
        Matcher ctorMatcher = ctorParamPattern.matcher(content);
        if (ctorMatcher.find()) {
            content = ctorMatcher.replaceFirst("$1@Lazy $2");
            modified = true;
        }

        // 2. Field injection: @Autowired private TargetBean target;
        if (!modified) {
            Pattern fieldPattern = Pattern.compile(
                    "(@Autowired\\s*(?:private|protected|public)?\\s+(?:final\\s+)?)"
                            + Pattern.quote(targetBean) + "(\\s+[a-zA-Z0-9_]+\\s*;)"
            );
            Matcher fieldMatcher = fieldPattern.matcher(content);
            if (fieldMatcher.find()) {
                content = fieldMatcher.replaceFirst("@Lazy\n    $1" + targetBean + "$2");
                modified = true;
            }
        }

        // 3. Direct field injection without @Autowired (Lombok or general field)
        if (!modified) {
            Pattern directFieldPattern = Pattern.compile(
                    "((?:private|protected|public)\\s+(?:final\\s+)?)"
                            + Pattern.quote(targetBean) + "(\\s+[a-zA-Z0-9_]+\\s*;)"
            );
            Matcher directMatcher = directFieldPattern.matcher(content);
            if (directMatcher.find()) {
                content = directMatcher.replaceFirst("@Lazy\n    $1" + targetBean + "$2");
                modified = true;
            }
        }

        if (modified) {
            content = ensureImport(content, "org.springframework.context.annotation.Lazy");
        }

        return content;
    }

    private static Set<String> extractDependencies(String className, String content) {
        Set<String> deps = new LinkedHashSet<>();

        // Match @Autowired fields
        Matcher fm = AUTOWIRED_FIELD_PATTERN.matcher(content);
        while (fm.find()) {
            String depType = fm.group(2);
            if (!depType.equals(className)) {
                deps.add(depType);
            }
        }

        // Match constructor parameters
        Pattern ctorPattern = Pattern.compile(
                "(?:public|protected|private)?\\s*" + Pattern.quote(className) + "\\s*\\(([^)]*)\\)"
        );
        Matcher cm = ctorPattern.matcher(content);
        if (cm.find()) {
            String params = cm.group(1);
            String[] paramList = params.split(",");
            for (String param : paramList) {
                String trimmed = param.trim();
                if (!trimmed.isEmpty()) {
                    String[] tokens = trimmed.split("\\s+");
                    if (tokens.length >= 2) {
                        String type = tokens[tokens.length - 2];
                        type = type.replace("@Lazy", "").replace("@Autowired", "").trim();
                        if (!type.isEmpty() && !type.equals(className) && Character.isUpperCase(type.charAt(0))) {
                            deps.add(type);
                        }
                    }
                }
            }
        }

        return deps;
    }

    private static List<List<String>> detectCycles(Map<String, Set<String>> graph) {
        List<List<String>> cycles = new ArrayList<>();
        Set<String> visited = new HashSet<>();
        List<String> path = new ArrayList<>();
        Set<String> inPath = new HashSet<>();
        Set<String> recordedCycleKeys = new HashSet<>();

        for (String node : graph.keySet()) {
            if (!visited.contains(node)) {
                dfsCycle(node, graph, visited, path, inPath, cycles, recordedCycleKeys);
            }
        }

        return cycles;
    }

    private static void dfsCycle(
            String current,
            Map<String, Set<String>> graph,
            Set<String> visited,
            List<String> path,
            Set<String> inPath,
            List<List<String>> cycles,
            Set<String> recordedCycleKeys
    ) {
        visited.add(current);
        path.add(current);
        inPath.add(current);

        Set<String> neighbors = graph.getOrDefault(current, Collections.emptySet());
        for (String neighbor : neighbors) {
            if (inPath.contains(neighbor)) {
                int cycleStart = path.indexOf(neighbor);
                List<String> cycle = new ArrayList<>(path.subList(cycleStart, path.size()));
                cycle.add(neighbor);

                // Deduplicate cycle signature
                List<String> canonical = new ArrayList<>(cycle.subList(0, cycle.size() - 1));
                Collections.sort(canonical);
                String key = String.join(",", canonical);
                if (recordedCycleKeys.add(key)) {
                    cycles.add(cycle);
                }
            } else if (!visited.contains(neighbor)) {
                dfsCycle(neighbor, graph, visited, path, inPath, cycles, recordedCycleKeys);
            }
        }

        path.remove(path.size() - 1);
        inPath.remove(current);
    }

    private static String ensureImport(String content, String fqcn) {
        if (content.contains("import " + fqcn + ";")) {
            return content;
        }
        int pkgIndex = content.indexOf("package ");
        if (pkgIndex >= 0) {
            int pkgEnd = content.indexOf(";", pkgIndex);
            if (pkgEnd >= 0) {
                return content.substring(0, pkgEnd + 1) + "\n\nimport " + fqcn + ";" + content.substring(pkgEnd + 1);
            }
        }
        return "import " + fqcn + ";\n" + content;
    }
}
