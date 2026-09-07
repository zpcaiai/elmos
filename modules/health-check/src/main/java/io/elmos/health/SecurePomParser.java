package io.elmos.health;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import java.nio.file.Path;
import java.util.*;

final class SecurePomParser {
    record PomData(HealthModels.Module module, List<HealthModels.Dependency> dependencies,
                   Map<String, String> properties, boolean junit, boolean coverage,
                   String springBootVersion, String springCloudVersion) {}

    PomData parse(Path root, Path pom) {
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            factory.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false);
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            factory.setXIncludeAware(false); factory.setExpandEntityReferences(false);
            Document document = factory.newDocumentBuilder().parse(pom.toFile());
            Element project = document.getDocumentElement();
            Map<String, String> properties = properties(project);
            Element parent = child(project, "parent");
            String group = first(text(project, "groupId"), text(parent, "groupId"));
            String artifact = text(project, "artifactId");
            String version = first(text(project, "version"), text(parent, "version"));
            properties.putIfAbsent("project.groupId", group); properties.putIfAbsent("project.artifactId", artifact);
            properties.putIfAbsent("project.version", version); properties.putIfAbsent("pom.version", version);
            group = resolve(group, properties); artifact = resolve(artifact, properties); version = resolve(version, properties);
            List<String> declaredModules = childrenText(child(project, "modules"), "module");
            String relative = normalize(root, pom.getParent());
            HealthModels.Module module = new HealthModels.Module(relative, group, artifact, version,
                    HealthModels.BuildSystem.MAVEN, declaredModules);

            Map<String, String> managed = new HashMap<>();
            Element management = child(child(project, "dependencyManagement"), "dependencies");
            for (Element dep : children(management, "dependency")) {
                String g = resolve(text(dep, "groupId"), properties), a = resolve(text(dep, "artifactId"), properties);
                managed.put(g + ":" + a, resolve(text(dep, "version"), properties));
            }
            List<HealthModels.Dependency> dependencies = new ArrayList<>();
            boolean junit = false;
            Element deps = child(project, "dependencies");
            for (Element dep : children(deps, "dependency")) {
                String g = resolve(text(dep, "groupId"), properties), a = resolve(text(dep, "artifactId"), properties);
                String v = resolve(text(dep, "version"), properties);
                if (blank(v)) v = managed.get(g + ":" + a);
                String scope = first(resolve(text(dep, "scope"), properties), "compile");
                dependencies.add(new HealthModels.Dependency(g, a, v, scope, relative, true));
                junit |= (g + ":" + a).toLowerCase(Locale.ROOT).contains("junit");
            }
            String boot = resolve(first(properties.get("spring-boot.version"),
                    parent != null && "org.springframework.boot".equals(text(parent, "groupId")) ? text(parent, "version") : null,
                    managed.get("org.springframework.boot:spring-boot-dependencies")), properties);
            String cloud = resolve(first(properties.get("spring-cloud.version"),
                    managed.get("org.springframework.cloud:spring-cloud-dependencies")), properties);
            boolean coverage = hasPlugin(project, "org.jacoco", "jacoco-maven-plugin");
            return new PomData(module, dependencies, properties, junit, coverage, boot, cloud);
        } catch (Exception error) {
            throw new IllegalArgumentException("POM_PARSE_FAILED:" + normalize(root, pom), error);
        }
    }

    private static Map<String, String> properties(Element project) {
        Map<String, String> values = new HashMap<>(); Element properties = child(project, "properties");
        if (properties == null) return values;
        NodeList nodes = properties.getChildNodes();
        for (int i = 0; i < nodes.getLength(); i++) if (nodes.item(i) instanceof Element element)
            values.put(element.getTagName(), element.getTextContent().trim());
        return values;
    }
    private static boolean hasPlugin(Element project, String group, String artifact) {
        NodeList plugins = project.getElementsByTagName("plugin");
        for (int i = 0; i < plugins.getLength(); i++) if (plugins.item(i) instanceof Element plugin)
            if (group.equals(first(text(plugin, "groupId"), "org.apache.maven.plugins")) && artifact.equals(text(plugin, "artifactId"))) return true;
        return false;
    }
    private static String resolve(String value, Map<String, String> properties) {
        if (value == null) return null; String resolved = value;
        for (int depth = 0; depth < 8; depth++) {
            int start = resolved.indexOf("${"); if (start < 0) break;
            int end = resolved.indexOf('}', start + 2); if (end < 0) break;
            String key = resolved.substring(start + 2, end), replacement = properties.get(key);
            if (replacement == null) break;
            resolved = resolved.substring(0, start) + replacement + resolved.substring(end + 1);
        }
        return resolved.trim();
    }
    private static List<Element> children(Element parent, String name) {
        if (parent == null) return List.of(); List<Element> result = new ArrayList<>(); NodeList nodes = parent.getChildNodes();
        for (int i = 0; i < nodes.getLength(); i++) if (nodes.item(i) instanceof Element e && name.equals(e.getTagName())) result.add(e);
        return result;
    }
    private static List<String> childrenText(Element parent, String name) { return children(parent, name).stream().map(Element::getTextContent).map(String::trim).toList(); }
    private static Element child(Element parent, String name) { return children(parent, name).stream().findFirst().orElse(null); }
    private static String text(Element parent, String name) { Element value = child(parent, name); return value == null ? null : value.getTextContent().trim(); }
    private static String first(String... values) { for (String value : values) if (!blank(value)) return value; return null; }
    private static boolean blank(String value) { return value == null || value.isBlank(); }
    private static String normalize(Path root, Path path) { String value = root.relativize(path).toString().replace('\\', '/'); return value.isBlank() ? "." : value; }
}
