package io.elmos.intake;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.tomlj.Toml;
import org.tomlj.TomlArray;
import org.tomlj.TomlParseResult;
import org.tomlj.TomlTable;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.xml.sax.ErrorHandler;
import org.xml.sax.SAXParseException;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

import static io.elmos.intake.IntakeModels.*;

/** Uses format-aware XML, JSON and TOML parsers; opaque build DSL values are explicitly unresolved. */
final class BuildManifestInspector {
    private final ObjectMapper json = new ObjectMapper();

    BuildModel inspect(Path root, RepositorySnapshot snapshot) {
        List<BuildProject> projects = new ArrayList<>(); List<String> unresolved = new ArrayList<>();
        List<String> privateSources = new ArrayList<>();
        Set<String> paths = snapshot.files().stream().map(FileEntry::path).collect(java.util.stream.Collectors.toSet());
        Map<String, String> centralNugetVersions = centralNugetVersions(root, snapshot, unresolved);
        for (FileEntry file : snapshot.files()) {
            String name = file.path().substring(file.path().lastIndexOf('/') + 1).toLowerCase(Locale.ROOT);
            if (file.secretLike() || file.binary() || file.vendored() || file.generated()) continue;
            Path absolute = root.resolve(file.path()).normalize();
            try {
                if (name.equals("pom.xml")) projects.add(parseMaven(root, absolute, paths, privateSources));
                else if (name.equals("build.gradle") || name.equals("build.gradle.kts")) projects.add(opaqueGradle(root, absolute, paths));
                else if (name.equals("pyproject.toml")) projects.add(parsePyproject(root, absolute, paths));
                else if (name.equals("requirements.txt") && !paths.contains(join(relative(root, absolute.getParent()), "pyproject.toml"))) projects.add(parseRequirements(root, absolute, paths));
                else if (name.equals("setup.py") && !paths.contains(join(relative(root, absolute.getParent()), "pyproject.toml")) && !paths.contains(join(relative(root, absolute.getParent()), "requirements.txt"))) projects.add(opaqueSetupPy(root, absolute, paths));
                else if (name.equals("package.json")) projects.add(parsePackageJson(root, absolute, paths));
                else if (name.endsWith(".csproj")) projects.add(parseCsproj(root, absolute, paths, centralNugetVersions));
            } catch (RuntimeException error) {
                unresolved.add(file.path() + ":" + safeCode(error));
            }
        }
        projects.sort(Comparator.comparing(BuildProject::projectId));
        privateSources.sort(String::compareTo); unresolved.sort(String::compareTo);
        return new BuildModel("1.0", snapshot.snapshotId(), projects, privateSources.stream().distinct().toList(), unresolved);
    }

    private BuildProject parseMaven(Path root, Path pom, Set<String> paths, List<String> privateSources) {
        Document document = secureXml(pom); Element project = document.getDocumentElement(); String base = relative(root, pom.getParent());
        Map<String, String> properties = new TreeMap<>();
        Element props = child(project, "properties");
        if (props != null) for (Node node = props.getFirstChild(); node != null; node = node.getNextSibling())
            if (node instanceof Element element) properties.put(local(element), text(element));
        String group = value(project, "groupId"); String artifact = value(project, "artifactId"); String version = value(project, "version");
        Element parent = child(project, "parent");
        if (group == null && parent != null) group = value(parent, "groupId");
        if (version == null && parent != null) version = value(parent, "version");
        List<Dependency> dependencies = new ArrayList<>();
        Element dependenciesElement = child(project, "dependencies");
        if (dependenciesElement != null) for (Element dependency : children(dependenciesElement, "dependency")) {
            String g = value(dependency, "groupId"), a = value(dependency, "artifactId"), v = resolve(value(dependency, "version"), properties);
            String scope = Optional.ofNullable(value(dependency, "scope")).orElse("compile");
            dependencies.add(new Dependency("maven", safe(g) + ":" + safe(a), v, scope, relative(root, pom), true, resolved(v)));
        }
        List<String> plugins = new ArrayList<>(); Element build = child(project, "build");
        if (build != null && child(build, "plugins") != null) for (Element plugin : children(child(build, "plugins"), "plugin"))
            plugins.add(safe(value(plugin, "groupId")) + ":" + safe(value(plugin, "artifactId")));
        List<String> repositories = new ArrayList<>(); Element repositoriesElement = child(project, "repositories");
        if (repositoriesElement != null) for (Element repository : children(repositoriesElement, "repository")) {
            String url = value(repository, "url"); if (url != null) { repositories.add(url); if (!url.contains("repo.maven.apache.org") && !url.contains("repo1.maven.org")) privateSources.add(url); }
        }
        List<String> modulePaths = new ArrayList<>(); Element modules = child(project, "modules");
        if (modules != null) for (Element module : children(modules, "module")) modulePaths.add(text(module));
        Map<String, String> compiler = new TreeMap<>();
        for (String key : List.of("maven.compiler.release", "maven.compiler.source", "maven.compiler.target", "java.version"))
            if (properties.containsKey(key)) compiler.put(key, properties.get(key));
        List<String> unresolved = new ArrayList<>();
        dependencies.stream().filter(dependency -> !dependency.resolved()).forEach(dependency -> unresolved.add("dependency-version:" + dependency.name()));
        if (!modulePaths.isEmpty()) unresolved.addAll(modulePaths.stream().filter(module -> !paths.contains(join(base, module, "pom.xml"))).map(module -> "declared-module-not-found:" + module).toList());
        String executable = paths.contains(join(base, "mvnw")) ? "./mvnw" : "mvn";
        return new BuildProject(projectId("maven", base, safe(group) + ":" + safe(artifact)), Language.JAVA, "maven",
                existing(paths, join(base, "src/main/java")), existing(paths, join(base, "src/test/java")),
                existing(paths, join(base, "src/main/resources")), List.of(join(base, "target/generated-sources")),
                dependencies, plugins, repositories, compiler,
                List.of(new BuildCommand(List.of(executable, "test"), true, true)),
                List.of(new BuildCommand(List.of(executable, "-DskipTests", "package"), true, true)), unresolved);
    }

    private BuildProject opaqueGradle(Path root, Path build, Set<String> paths) {
        String base = relative(root, build.getParent()); String executable = paths.contains(join(base, "gradlew")) ? "./gradlew" : "gradle";
        return new BuildProject(projectId("gradle", base, build.getFileName().toString()), Language.JAVA, "gradle",
                existing(paths, join(base, "src/main/java")), existing(paths, join(base, "src/test/java")),
                existing(paths, join(base, "src/main/resources")), List.of(join(base, "build/generated")), List.of(), List.of(), List.of(), Map.of(),
                List.of(new BuildCommand(List.of(executable, "test", "--no-daemon"), true, true)),
                List.of(new BuildCommand(List.of(executable, "build", "--no-daemon"), true, true)),
                List.of("Gradle DSL is not evaluated during intake; dependencies require an approved Tooling API export"));
    }

    private BuildProject parsePyproject(Path root, Path file, Set<String> paths) {
        TomlParseResult toml;
        try { toml = Toml.parse(Files.readString(file, StandardCharsets.UTF_8)); }
        catch (IOException error) { throw new IllegalArgumentException("PYPROJECT_READ_FAILED", error); }
        if (toml.hasErrors()) throw new IllegalArgumentException("PYPROJECT_PARSE_FAILED");
        String base = relative(root, file.getParent()); List<Dependency> dependencies = new ArrayList<>(); List<String> unresolved = new ArrayList<>();
        TomlTable projectTable = toml.getTable("project");
        TomlArray projectDependencies = projectTable == null ? null : projectTable.getArray("dependencies");
        if (projectDependencies != null) for (int i = 0; i < projectDependencies.size(); i++) addPep508(dependencies, projectDependencies.getString(i), "runtime", relative(root, file));
        TomlTable optional = projectTable == null ? null : projectTable.getTable("optional-dependencies");
        if (optional != null) for (String extra : optional.keySet()) {
            TomlArray values = optional.getArray(extra); if (values != null) for (int i = 0; i < values.size(); i++) addPep508(dependencies, values.getString(i), "extra:" + extra, relative(root, file));
        }
        TomlTable toolTable = toml.getTable("tool"); TomlTable poetryTable = toolTable == null ? null : toolTable.getTable("poetry");
        TomlTable poetry = poetryTable == null ? null : poetryTable.getTable("dependencies");
        if (poetry != null) for (String name : poetry.keySet()) {
            Object value = poetry.get(name); String version = value instanceof String text ? text : null;
            dependencies.add(new Dependency("pypi", name, version, "runtime", relative(root, file), true, resolved(version)));
            if (version == null) unresolved.add("poetry-complex-dependency:" + name);
        }
        String tool = paths.contains(join(base, "uv.lock")) ? "uv" : paths.contains(join(base, "poetry.lock")) ? "poetry" : "pip";
        List<BuildCommand> restore = switch (tool) {
            case "uv" -> List.of(new BuildCommand(List.of("uv", "sync", "--frozen"), true, true));
            case "poetry" -> List.of(new BuildCommand(List.of("poetry", "install", "--no-interaction"), true, true));
            default -> List.of(new BuildCommand(List.of("python", "-m", "pip", "install", "."), true, true));
        };
        String projectName = projectTable == null ? null : projectTable.getString("name");
        String requiresPython = projectTable == null ? null : projectTable.getString("requires-python");
        return new BuildProject(projectId("python", base, Optional.ofNullable(projectName).orElse("project")), Language.PYTHON, tool,
                existingAny(paths, base, Arrays.asList("src", findPythonPackage(toml))), existingAny(paths, base, List.of("tests", "test")), List.of(), List.of(),
                dependencies, List.of(), List.of(), Map.of("requires-python", safe(requiresPython)),
                List.of(new BuildCommand(List.of("pytest"), false, true)), restore, unresolved);
    }

    private BuildProject parsePackageJson(Path root, Path file, Set<String> paths) {
        JsonNode packageJson;
        try { packageJson = json.readTree(file.toFile()); } catch (IOException error) { throw new IllegalArgumentException("PACKAGE_JSON_PARSE_FAILED", error); }
        String base = relative(root, file.getParent()); List<Dependency> dependencies = new ArrayList<>();
        addNpm(dependencies, packageJson.path("dependencies"), "runtime", relative(root, file));
        addNpm(dependencies, packageJson.path("devDependencies"), "dev", relative(root, file));
        addNpm(dependencies, packageJson.path("peerDependencies"), "peer", relative(root, file));
        addNpm(dependencies, packageJson.path("optionalDependencies"), "optional", relative(root, file));
        String manager = paths.contains(join(base, "pnpm-lock.yaml")) ? "pnpm" : paths.contains(join(base, "yarn.lock")) ? "yarn" : "npm";
        Language language = paths.stream().anyMatch(path -> path.equals(join(base, "tsconfig.json")) || path.startsWith(join(base, "src/") ) && (path.endsWith(".ts") || path.endsWith(".tsx"))) ? Language.TYPESCRIPT : Language.JAVASCRIPT;
        String install = manager.equals("pnpm") ? "pnpm install --frozen-lockfile" : manager.equals("yarn") ? "yarn install --immutable" : "npm ci --ignore-scripts";
        List<String> build = scriptCommand(manager, packageJson.path("scripts"), "build"); List<String> test = scriptCommand(manager, packageJson.path("scripts"), "test");
        List<String> unresolved = new ArrayList<>(); if (packageJson.has("workspaces")) unresolved.add("workspace membership is detected; nested package.json files are modeled independently");
        return new BuildProject(projectId("npm", base, packageJson.path("name").asText("package")), language, manager,
                existingAny(paths, base, List.of("src", "app", "lib")), existingAny(paths, base, List.of("test", "tests", "__tests__")),
                existingAny(paths, base, List.of("public", "assets")), List.of(join(base, "dist"), join(base, ".next")), dependencies, List.of(), List.of(), Map.of(),
                test.isEmpty() ? List.of() : List.of(new BuildCommand(test, false, true)),
                List.of(new BuildCommand(Arrays.asList(install.split(" ")), true, !install.contains("--ignore-scripts"))), unresolved);
    }

    private BuildProject parseRequirements(Path root, Path file, Set<String> paths) {
        String base = relative(root, file.getParent()); List<Dependency> dependencies = new ArrayList<>(); List<String> unresolved = new ArrayList<>();
        try {
            for (String raw : Files.readAllLines(file, StandardCharsets.UTF_8)) {
                String line = raw.strip(); if (line.isBlank() || line.startsWith("#")) continue;
                if (line.startsWith("-") || line.contains("://") || line.startsWith("git+")) unresolved.add("non-registry-requirement:" + line);
                else addPep508(dependencies, line, "runtime", relative(root, file));
            }
        } catch (IOException error) { throw new IllegalArgumentException("REQUIREMENTS_READ_FAILED", error); }
        return new BuildProject(projectId("python", base, "requirements"), Language.PYTHON, "pip",
                existingAny(paths, base, List.of("src", ".")), existingAny(paths, base, List.of("tests", "test")), List.of(), List.of(),
                dependencies, List.of(), List.of(), Map.of(), List.of(new BuildCommand(List.of("pytest"), false, true)),
                List.of(new BuildCommand(List.of("python", "-m", "pip", "install", "-r", "requirements.txt"), true, true)), unresolved);
    }

    private BuildProject opaqueSetupPy(Path root, Path file, Set<String> paths) {
        String base = relative(root, file.getParent());
        return new BuildProject(projectId("python", base, "setup.py"), Language.PYTHON, "setuptools",
                existingAny(paths, base, List.of("src", ".")), existingAny(paths, base, List.of("tests", "test")), List.of(), List.of(), List.of(), List.of(), List.of(), Map.of(),
                List.of(new BuildCommand(List.of("pytest"), false, true)), List.of(new BuildCommand(List.of("python", "-m", "pip", "install", "."), true, true)),
                List.of("setup.py is executable Python and is not evaluated during intake; export PEP 621 metadata or resolve in the approved sandbox"));
    }

    private BuildProject parseCsproj(Path root, Path file, Set<String> paths, Map<String, String> centralVersions) {
        Document document = secureXml(file); Element project = document.getDocumentElement(); String base = relative(root, file.getParent());
        List<Dependency> dependencies = new ArrayList<>();
        for (Element itemGroup : children(project, "ItemGroup")) for (Element reference : children(itemGroup, "PackageReference")) {
            String name = reference.getAttribute("Include"); String version = reference.getAttribute("Version");
            if (version.isBlank()) version = value(reference, "Version"); if (version == null || version.isBlank()) version = centralVersions.get(name);
            dependencies.add(new Dependency("nuget", name, version, "compile", relative(root, file), true, resolved(version)));
        }
        Map<String, String> compiler = new TreeMap<>();
        for (Element propertyGroup : children(project, "PropertyGroup")) for (String key : List.of("TargetFramework", "TargetFrameworks", "LangVersion", "Nullable")) {
            String value = value(propertyGroup, key); if (value != null) compiler.putIfAbsent(key, value);
        }
        List<String> unresolved = dependencies.stream().filter(dependency -> !dependency.resolved()).map(dependency -> "central-or-inherited-version:" + dependency.name()).toList();
        return new BuildProject(projectId("dotnet", base, file.getFileName().toString()), Language.CSHARP, "dotnet",
                existing(paths, base), existingAny(paths, base, List.of("test", "tests")), List.of(), List.of(join(base, "obj")), dependencies, List.of(), List.of(), compiler,
                List.of(new BuildCommand(List.of("dotnet", "test", file.getFileName().toString(), "--no-restore"), false, true)),
                List.of(new BuildCommand(List.of("dotnet", "restore", file.getFileName().toString()), true, true), new BuildCommand(List.of("dotnet", "build", file.getFileName().toString(), "--no-restore"), false, true)), unresolved);
    }

    private static Map<String, String> centralNugetVersions(Path root, RepositorySnapshot snapshot, List<String> unresolved) {
        Map<String, String> versions = new TreeMap<>();
        for (FileEntry file : snapshot.files()) if (file.path().toLowerCase(Locale.ROOT).endsWith("directory.packages.props")) {
            try {
                Document document = secureXml(root.resolve(file.path()));
                for (Element itemGroup : children(document.getDocumentElement(), "ItemGroup")) for (Element version : children(itemGroup, "PackageVersion")) {
                    String name = version.getAttribute("Include"), value = version.getAttribute("Version"); if (value.isBlank()) value = value(version, "Version");
                    if (!name.isBlank() && value != null && !value.isBlank()) versions.put(name, value);
                }
            } catch (RuntimeException error) { unresolved.add(file.path() + ":" + safeCode(error)); }
        }
        return versions;
    }

    private static void addPep508(List<Dependency> target, String declaration, String scope, String source) {
        if (declaration == null || declaration.isBlank()) return;
        String trimmed = declaration.strip(); int marker = trimmed.indexOf(';'); if (marker >= 0) trimmed = trimmed.substring(0, marker).strip();
        int split = 0; while (split < trimmed.length() && (Character.isLetterOrDigit(trimmed.charAt(split)) || "-_.[]".indexOf(trimmed.charAt(split)) >= 0)) split++;
        String name = trimmed.substring(0, split); String version = split < trimmed.length() ? trimmed.substring(split).strip() : "*";
        target.add(new Dependency("pypi", name, version, scope, source, true, !name.isBlank() && !version.contains("${")));
    }
    private static void addNpm(List<Dependency> target, JsonNode node, String scope, String source) {
        if (!node.isObject()) return;
        node.fields().forEachRemaining(entry -> target.add(new Dependency("npm", entry.getKey(), entry.getValue().asText(), scope, source, true, !entry.getValue().asText().isBlank())));
    }
    private static List<String> scriptCommand(String manager, JsonNode scripts, String name) {
        if (!scripts.has(name)) return List.of(); return manager.equals("npm") ? List.of("npm", "run", name) : List.of(manager, name);
    }
    private static String findPythonPackage(TomlParseResult result) {
        TomlTable tool = result.getTable("tool"); TomlTable poetry = tool == null ? null : tool.getTable("poetry");
        return poetry == null ? null : poetry.getString("name");
    }
    private static Document secureXml(Path file) {
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance(); factory.setNamespaceAware(true);
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, ""); factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            var builder = factory.newDocumentBuilder();
            builder.setErrorHandler(new ErrorHandler() {
                @Override public void warning(SAXParseException exception) throws SAXParseException { throw exception; }
                @Override public void error(SAXParseException exception) throws SAXParseException { throw exception; }
                @Override public void fatalError(SAXParseException exception) throws SAXParseException { throw exception; }
            });
            return builder.parse(file.toFile());
        } catch (Exception error) { throw new IllegalArgumentException("XML_BUILD_MANIFEST_PARSE_FAILED", error); }
    }
    private static Element child(Element parent, String name) { for (Node node = parent.getFirstChild(); node != null; node = node.getNextSibling()) if (node instanceof Element element && local(element).equals(name)) return element; return null; }
    private static List<Element> children(Element parent, String name) { if (parent == null) return List.of(); List<Element> result = new ArrayList<>(); for (Node node = parent.getFirstChild(); node != null; node = node.getNextSibling()) if (node instanceof Element element && local(element).equals(name)) result.add(element); return result; }
    private static String value(Element parent, String name) { Element child = child(parent, name); return child == null ? null : text(child); }
    private static String text(Element element) { String value = element.getTextContent(); return value == null || value.isBlank() ? null : value.strip(); }
    private static String local(Element element) { return element.getLocalName() == null ? element.getNodeName() : element.getLocalName(); }
    private static String resolve(String value, Map<String, String> properties) { if (value != null && value.startsWith("${") && value.endsWith("}")) return properties.get(value.substring(2, value.length() - 1)); return value; }
    private static boolean resolved(String value) { return value != null && !value.isBlank() && !value.contains("${") && !value.contains("$("); }
    private static String projectId(String tool, String base, String identity) { return tool + ":" + (base.isBlank() ? "." : base) + ":" + identity; }
    private static String relative(Path root, Path path) { String value = root.relativize(path).toString().replace('\\', '/'); return value.isBlank() ? "." : value; }
    private static String join(String... parts) { String value = String.join("/", Arrays.stream(parts).filter(part -> part != null && !part.isBlank() && !part.equals(".")).toList()); return value.isBlank() ? "." : value.replaceAll("/+", "/"); }
    private static List<String> existing(Set<String> paths, String root) { String prefix = root.equals(".") ? "" : root + "/"; return paths.stream().anyMatch(path -> path.equals(root) || path.startsWith(prefix)) ? List.of(root) : List.of(); }
    private static List<String> existingAny(Set<String> paths, String base, List<String> candidates) { return candidates.stream().filter(Objects::nonNull).map(candidate -> join(base, candidate)).filter(candidate -> !existing(paths, candidate).isEmpty()).distinct().toList(); }
    private static String safe(String value) { return value == null ? "" : value; }
    private static String safeCode(RuntimeException error) { String message = error.getMessage(); return message == null || message.isBlank() ? error.getClass().getSimpleName() : message.replaceAll("[\r\n]+", " "); }
}
