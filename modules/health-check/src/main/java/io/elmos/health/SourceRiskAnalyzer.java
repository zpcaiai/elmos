package io.elmos.health;

import java.nio.file.Path;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class SourceRiskAnalyzer {
    record Result(List<HealthModels.Finding> findings, List<HealthModels.PublicApi> publicApis) {}
    private static final Pattern PACKAGE = Pattern.compile("(?m)^\\s*package\\s+([A-Za-z0-9_.]+)\\s*;");
    private static final Pattern IMPORT = Pattern.compile("(?m)^\\s*import\\s+(?:static\\s+)?([A-Za-z0-9_.]+)");
    private static final Pattern TYPE = Pattern.compile("(?:public\\s+)?(?:class|interface|record|enum)\\s+([A-Za-z_$][A-Za-z0-9_$]*)");
    private static final Pattern MAPPING = Pattern.compile("@(RequestMapping|GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping)\\s*(?:\\(([^)]*)\\))?");
    private static final Pattern PRIVATE_TRANSACTION = Pattern.compile("@Transactional(?:\\([^)]*\\))?\\s+(?:[A-Za-z@][^;{}]{0,240}\\s+)?private\\s", Pattern.DOTALL);
    private final ScanPolicy policy;

    SourceRiskAnalyzer(ScanPolicy policy) { this.policy = policy; }

    Result analyze(Path root, BuildInventory inventory) {
        List<HealthModels.Finding> findings = new ArrayList<>(); List<HealthModels.PublicApi> apis = new ArrayList<>();
        Map<String, Set<String>> graph = new TreeMap<>(); Set<String> projectPackages = new HashSet<>();
        Map<Path, String> contentByFile = new LinkedHashMap<>();
        List<Path> all = new ArrayList<>(inventory.javaFiles()); all.addAll(inventory.testFiles());
        for (Path file : all) {
            String content = ProjectDiscovery.read(file); contentByFile.put(file, content); Matcher matcher = PACKAGE.matcher(content);
            if (matcher.find()) projectPackages.add(matcher.group(1));
        }
        for (Map.Entry<Path, String> entry : contentByFile.entrySet()) {
            Path file = entry.getKey(); String content = entry.getValue(), location = normalize(root, file);
            Matcher packageMatcher = PACKAGE.matcher(content); String pkg = packageMatcher.find() ? packageMatcher.group(1) : "<default>";
            graph.computeIfAbsent(pkg, ignored -> new TreeSet<>());
            Matcher imports = IMPORT.matcher(content);
            while (imports.find()) {
                String imported = imports.group(1); String target = longestPackage(imported, projectPackages);
                if (target != null && !target.equals(pkg)) graph.get(pkg).add(target);
            }
            int lines = content.split("\\R", -1).length;
            if (lines >= policy.oversizedClassLines()) findings.add(finding("OVERSIZED_JAVA_TYPE", "ARCHITECTURE", HealthModels.Severity.MEDIUM, location,
                    "Java source has " + lines + " lines", Map.of("lines", Integer.toString(lines))));
            int branches = tokenCount(content, " if ", " if(", " for ", " for(", " while ", " while(", " case ", " catch ", "&&", "||", "?");
            if (branches >= policy.complexMethodBranches()) findings.add(finding("HIGH_BRANCH_DENSITY", "COMPLEXITY", HealthModels.Severity.MEDIUM, location,
                    "Source contains " + branches + " branch tokens; method-level parser validation is required", Map.of("branchTokens", Integer.toString(branches))));
            if (content.contains("javax.persistence") || content.contains("javax.validation") || content.contains("javax.servlet"))
                findings.add(finding("LEGACY_JAVAX_API", "COMPATIBILITY", HealthModels.Severity.HIGH, location, "Jakarta namespace migration is required", Map.of()));
            if (PRIVATE_TRANSACTION.matcher(content).find()) findings.add(finding("PRIVATE_TRANSACTIONAL_METHOD", "TRANSACTION", HealthModels.Severity.HIGH, location,
                    "Private transactional method may not be proxied", Map.of()));
            if (content.contains("@Cacheable") && !content.contains("@CacheEvict") && !content.contains("@CachePut"))
                findings.add(finding("CACHE_INVALIDATION_UNPROVEN", "CACHE", HealthModels.Severity.MEDIUM, location,
                        "Cache read annotation found without local invalidation evidence", Map.of()));
            if (Pattern.compile("createNativeQuery\\s*\\([^)]*\\+", Pattern.DOTALL).matcher(content).find())
                findings.add(finding("DYNAMIC_NATIVE_QUERY", "DATABASE", HealthModels.Severity.HIGH, location,
                        "Concatenated native query requires injection and compatibility review", Map.of()));
            if (content.contains("@RestController") || content.contains("@Controller")) {
                Matcher type = TYPE.matcher(content); String owner = type.find() ? pkg + "." + type.group(1) : pkg;
                Matcher mapping = MAPPING.matcher(content);
                while (mapping.find()) apis.add(new HealthModels.PublicApi("HTTP", owner,
                        mapping.group(1) + ":" + normalizeMapping(mapping.group(2)), location));
            }
            if ((content.contains("public interface") || content.contains("public record")) && location.contains("/api/")) {
                Matcher type = TYPE.matcher(content); if (type.find()) apis.add(new HealthModels.PublicApi("JAVA", pkg + "." + type.group(1), "public-type", location));
            }
        }
        for (String cycle : cycles(graph)) findings.add(finding("PACKAGE_DEPENDENCY_CYCLE", "ARCHITECTURE", HealthModels.Severity.HIGH, ".",
                "Package cycle: " + cycle, Map.of("cycle", cycle)));
        apis.sort(Comparator.comparing(HealthModels.PublicApi::location).thenComparing(HealthModels.PublicApi::signature));
        return new Result(findings, apis);
    }

    private static Set<String> cycles(Map<String, Set<String>> graph) {
        Set<String> result = new TreeSet<>();
        for (String start : graph.keySet()) findCycles(start, start, graph, new LinkedHashSet<>(), result);
        return result;
    }
    private static void findCycles(String start, String current, Map<String, Set<String>> graph, LinkedHashSet<String> path, Set<String> result) {
        if (path.size() > 12 || !path.add(current)) return;
        for (String next : graph.getOrDefault(current, Set.of())) {
            if (next.equals(start) && path.size() > 1) {
                List<String> cycle = new ArrayList<>(path); int min = 0;
                for (int i = 1; i < cycle.size(); i++) if (cycle.get(i).compareTo(cycle.get(min)) < 0) min = i;
                Collections.rotate(cycle, -min); result.add(String.join(" -> ", cycle) + " -> " + cycle.getFirst());
            } else if (!path.contains(next)) findCycles(start, next, graph, path, result);
        }
        path.remove(current);
    }
    private static String longestPackage(String imported, Set<String> packages) { return packages.stream().filter(p -> imported.equals(p) || imported.startsWith(p + ".")).max(Comparator.comparingInt(String::length)).orElse(null); }
    private static int tokenCount(String content, String... tokens) { int count = 0; for (String token : tokens) { int from = 0; while ((from = content.indexOf(token, from)) >= 0) { count++; from += token.length(); } } return count; }
    private static String normalizeMapping(String args) { if (args == null || args.isBlank()) return "/"; String clean = args.replaceAll("\\s+", " ").trim(); return clean.length() > 200 ? clean.substring(0, 200) : clean; }
    private static String normalize(Path root, Path path) { return root.relativize(path).toString().replace('\\', '/'); }
    private static HealthModels.Finding finding(String code, String category, HealthModels.Severity severity, String location, String message, Map<String,String> attributes) {
        return new HealthModels.Finding(code, category, severity, location, message, HealthModels.EvidenceStatus.FAIL, attributes);
    }
}
