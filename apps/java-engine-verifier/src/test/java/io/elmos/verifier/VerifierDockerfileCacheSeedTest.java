package io.elmos.verifier;

import org.junit.jupiter.api.Test;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import javax.xml.parsers.DocumentBuilderFactory;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class VerifierDockerfileCacheSeedTest {
    private static final Set<String> REPRESENTATIVE_DEPENDENCIES = Set.of(
            "spring-boot-starter-web",
            "spring-boot-starter-actuator",
            "spring-boot-starter-validation",
            "spring-boot-starter-security",
            "spring-boot-starter-data-jpa",
            "spring-kafka",
            "h2",
            "spring-boot-starter-test"
    );

    private record TargetSeed(String boot, String java, String javaRange, String relativePom) {}

    private static final List<TargetSeed> TARGETS = List.of(
            new TargetSeed("2.7.18", "17", "[17,18)",
                    "apps/java-engine-verifier/cache-seeds/spring-boot-2.7.18-java-17/pom.xml"),
            new TargetSeed("3.2.12", "17", "[17,18)",
                    "apps/java-engine-verifier/cache-seeds/spring-boot-3.2.12-java-17/pom.xml"),
            new TargetSeed("3.5.3", "21", "[21,22)",
                    "apps/java-engine-verifier/cache-seeds/spring-boot-3.5.3-java-21/pom.xml")
    );

    @Test
    void everyAcceptedTargetHasAnExactRepresentativeSeedPom() throws Exception {
        Path root = repositoryRoot();
        for (TargetSeed target : TARGETS) {
            Document pom = parse(root.resolve(target.relativePom()));
            Element project = pom.getDocumentElement();
            Element parent = child(project, "parent");
            assertNotNull(parent, target.relativePom());
            assertEquals("org.springframework.boot", text(parent, "groupId"), target.relativePom());
            assertEquals("spring-boot-starter-parent", text(parent, "artifactId"), target.relativePom());
            assertEquals(target.boot(), text(parent, "version"), target.relativePom());

            Element properties = child(project, "properties");
            assertNotNull(properties, target.relativePom());
            assertEquals(target.java(), text(properties, "java.version"), target.relativePom());
            assertEquals(target.java(), text(properties, "maven.compiler.release"), target.relativePom());

            Set<String> artifacts = new LinkedHashSet<>();
            NodeList dependencies = project.getElementsByTagName("dependency");
            for (int index = 0; index < dependencies.getLength(); index += 1) {
                artifacts.add(text((Element) dependencies.item(index), "artifactId"));
            }
            assertTrue(artifacts.containsAll(REPRESENTATIVE_DEPENDENCIES),
                    target.relativePom() + " misses representative verifier dependencies: "
                            + difference(REPRESENTATIVE_DEPENDENCIES, artifacts));

            Element enforcer = plugin(project, "maven-enforcer-plugin");
            assertNotNull(enforcer, target.relativePom());
            assertEquals("3.6.1", text(enforcer, "version"), target.relativePom());
            NodeList ranges = enforcer.getElementsByTagName("requireJavaVersion");
            assertEquals(1, ranges.getLength(), target.relativePom());
            assertEquals(target.javaRange(), text((Element) ranges.item(0), "version"), target.relativePom());

            Element bootPlugin = plugin(project, "spring-boot-maven-plugin");
            assertNotNull(bootPlugin, target.relativePom());
            assertEquals("true", text(child(bootPlugin, "configuration"), "skip"), target.relativePom());
        }
    }

    @Test
    void dockerfileWarmsAllTuplesUnderTheirExactJdkIntoOneImmutableCache() throws Exception {
        Path root = repositoryRoot();
        String dockerfile = Files.readString(root.resolve("apps/java-engine-verifier/Dockerfile"));

        assertFalse(dockerfile.contains("framework-packs/spring-boot-2-7-18-to-3-5-3"),
                "cache seeding must not depend on the single 3.5.3 framework-pack fixture");
        for (TargetSeed target : TARGETS) {
            String block = Arrays.stream(dockerfile.split("(?m)^RUN "))
                    .filter(candidate -> candidate.contains("-f " + target.relativePom()))
                    .findFirst()
                    .orElseThrow(() -> new AssertionError("missing Docker cache seed " + target.relativePom()));
            String expectedHome = "17".equals(target.java())
                    ? "JAVA_HOME=/opt/java/openjdk-17"
                    : "JAVA_HOME=/opt/java/openjdk";
            assertTrue(block.contains(expectedHome), target.relativePom() + " is bound to the wrong JDK");
            assertTrue(block.contains("PATH=${JAVA_HOME}/bin:${PATH}")
                            || block.contains("PATH=/opt/java/openjdk-17/bin:${PATH}")
                            || block.contains("PATH=/opt/java/openjdk/bin:${PATH}"),
                    target.relativePom() + " does not put its exact JDK first on PATH");
            assertTrue(block.contains("-Dmaven.repo.local=/opt/elmos/maven-cache"), target.relativePom());
            assertTrue(block.contains(
                    "org.apache.maven.plugins:maven-dependency-plugin:3.8.1:go-offline"),
                    target.relativePom());
            assertTrue(block.contains("verify"), target.relativePom());
        }

        assertEquals(3, occurrences(dockerfile, "-Dmaven.repo.local=/opt/elmos/maven-cache"));
        assertTrue(dockerfile.contains(
                "COPY --from=build --chown=0:0 /opt/elmos/maven-cache /opt/elmos/maven-cache"));
        assertTrue(dockerfile.contains("RUN chmod -R a-w /opt/elmos/maven-cache"));
    }

    private static Path repositoryRoot() {
        Path cursor = Path.of(System.getProperty("user.dir")).toAbsolutePath().normalize();
        while (cursor != null) {
            if (Files.isRegularFile(cursor.resolve("apps/java-engine-verifier/pom.xml"))) return cursor;
            cursor = cursor.getParent();
        }
        throw new IllegalStateException("repository root is unavailable");
    }

    private static Document parse(Path path) throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
        factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        return factory.newDocumentBuilder().parse(path.toFile());
    }

    private static Element plugin(Element project, String artifactId) {
        NodeList plugins = project.getElementsByTagName("plugin");
        for (int index = 0; index < plugins.getLength(); index += 1) {
            Element plugin = (Element) plugins.item(index);
            if (artifactId.equals(text(plugin, "artifactId"))) return plugin;
        }
        return null;
    }

    private static Element child(Element parent, String name) {
        if (parent == null) return null;
        NodeList children = parent.getChildNodes();
        for (int index = 0; index < children.getLength(); index += 1) {
            Node node = children.item(index);
            if (node instanceof Element element && name.equals(element.getTagName())) return element;
        }
        return null;
    }

    private static String text(Element parent, String name) {
        Element element = child(parent, name);
        return element == null ? "" : element.getTextContent().trim();
    }

    private static Set<String> difference(Set<String> required, Set<String> actual) {
        Set<String> missing = new LinkedHashSet<>(required);
        missing.removeAll(actual);
        return missing;
    }

    private static int occurrences(String value, String needle) {
        return (value.length() - value.replace(needle, "").length()) / needle.length();
    }
}
