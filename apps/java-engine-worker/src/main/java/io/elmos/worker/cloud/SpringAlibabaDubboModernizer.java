package io.elmos.worker.cloud;

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
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.OutputKeys;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

/** Exact Boot 3.5 modernization rules for Spring Cloud Alibaba 2025.0 and Dubbo 3.3. */
public final class SpringAlibabaDubboModernizer {
    static final String ALIBABA_VERSION = "2025.0.0.0";
    static final String DUBBO_VERSION = "3.3.0";

    public record ModernizationResult(
            boolean modified,
            Set<String> modifiedFiles,
            List<String> rulesApplied,
            List<String> blockingObligations
    ) {}

    private static final Pattern VERSIONED_ALIBABA_BOM = Pattern.compile(
            "(?s)(<artifactId>spring-cloud-alibaba-dependencies</artifactId>"
                    + "(?:(?!</dependency>).)*?<version>)[^<]+(</version>)");
    private static final Pattern VERSIONED_DUBBO = Pattern.compile(
            "(?s)(<groupId>(?:com\\.alibaba|org\\.apache\\.dubbo)</groupId>\\s*"
                    + "<artifactId>dubbo-spring-boot-starter(?:3)?</artifactId>"
                    + "(?:(?!</dependency>).)*?<version>)[^<]+(</version>)");
    private static final Pattern LEGACY_DUBBO_COORDINATE = Pattern.compile(
            "(<groupId>)com\\.alibaba(</groupId>\\s*<artifactId>)"
                    + "dubbo-spring-boot-starter(</artifactId>)");

    private SpringAlibabaDubboModernizer() {}

    public static ModernizationResult modernize(Path projectRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        Set<String> filesChanged = new LinkedHashSet<>();
        List<String> rules = new ArrayList<>();
        List<String> blockers = new ArrayList<>();
        if (!Files.isDirectory(projectRoot)) {
            return new ModernizationResult(false, filesChanged, rules, List.of("project root does not exist"));
        }
        try (var files = Files.walk(projectRoot)) {
            for (Path file : files.filter(Files::isRegularFile).toList()) {
                String name = file.getFileName().toString();
                if (name.equals("pom.xml")) rewritePom(projectRoot, file, filesChanged, rules);
                else if (name.endsWith(".java")) rewriteJava(projectRoot, file, filesChanged, rules);
                else if (name.startsWith("bootstrap.") || name.startsWith("application.")) {
                    rewriteNacosConfig(projectRoot, file, filesChanged, rules);
                } else if (name.endsWith(".xml")) {
                    rewriteDubboXml(projectRoot, file, filesChanged, rules, blockers);
                }
            }
        } catch (IOException e) {
            blockers.add("IO:" + e.getClass().getSimpleName());
        }
        return new ModernizationResult(!filesChanged.isEmpty(), Set.copyOf(filesChanged),
                List.copyOf(rules), List.copyOf(blockers));
    }

    private static void rewritePom(Path root, Path pom, Set<String> changed, List<String> rules)
            throws IOException {
        String before = Files.readString(pom, StandardCharsets.UTF_8);
        String after = VERSIONED_ALIBABA_BOM.matcher(before)
                .replaceAll("$1" + ALIBABA_VERSION + "$2");
        if (after.contains("com.alibaba.cloud") && after.contains("spring-cloud-starter-alibaba-seata")) {
            after = after.replace("<artifactId>spring-cloud-starter-alibaba-seata</artifactId>",
                    "<artifactId>spring-cloud-starter-alibaba-seata</artifactId>");
        }
        after = LEGACY_DUBBO_COORDINATE.matcher(after)
                .replaceAll("$1org.apache.dubbo$2dubbo-spring-boot-starter3$3");
        Matcher dubbo = VERSIONED_DUBBO.matcher(after);
        after = dubbo.replaceAll("$1" + DUBBO_VERSION + "$2");
        if (!after.equals(before)) {
            Files.writeString(pom, after, StandardCharsets.UTF_8);
            changed.add(relative(root, pom));
            if (before.contains("spring-cloud-alibaba-dependencies")) rules.add("SCA_2025_0_BOOT_3_5_BOM");
            if (before.contains("dubbo-spring-boot-starter")) rules.add("DUBBO_3_3_BOOT3_STARTER");
        }
    }

    private static void rewriteJava(Path root, Path file, Set<String> changed, List<String> rules)
            throws IOException {
        String before = Files.readString(file, StandardCharsets.UTF_8);
        String after = before
                .replace("import com.alibaba.dubbo.config.annotation.Service;",
                        "import org.apache.dubbo.config.annotation.DubboService;")
                .replace("import com.alibaba.dubbo.config.annotation.Reference;",
                        "import org.apache.dubbo.config.annotation.DubboReference;")
                .replace("import org.apache.dubbo.config.annotation.Service;",
                        "import org.apache.dubbo.config.annotation.DubboService;")
                .replace("import org.apache.dubbo.config.annotation.Reference;",
                        "import org.apache.dubbo.config.annotation.DubboReference;");
        if (!after.equals(before)) {
            if (after.contains("import org.apache.dubbo.config.annotation.DubboService;")) {
                after = replaceAnnotation(after, "Service", "DubboService");
            }
            if (after.contains("import org.apache.dubbo.config.annotation.DubboReference;")) {
                after = replaceAnnotation(after, "Reference", "DubboReference");
            }
            Files.writeString(file, after, StandardCharsets.UTF_8);
            changed.add(relative(root, file));
            rules.add("DUBBO_LEGACY_ANNOTATIONS_TO_DUBBO_ANNOTATIONS");
        }
    }

    private static String replaceAnnotation(String source, String oldName, String newName) {
        StringBuilder result = new StringBuilder(source.length());
        boolean string = false;
        boolean character = false;
        boolean lineComment = false;
        boolean blockComment = false;
        for (int index = 0; index < source.length();) {
            char current = source.charAt(index);
            char next = index + 1 < source.length() ? source.charAt(index + 1) : '\0';
            if (lineComment) {
                result.append(current); index++;
                if (current == '\n') lineComment = false;
            } else if (blockComment) {
                result.append(current); index++;
                if (current == '*' && next == '/') { result.append(next); index++; blockComment = false; }
            } else if (string || character) {
                result.append(current); index++;
                if (current == '\\' && index < source.length()) result.append(source.charAt(index++));
                else if (string && current == '"') string = false;
                else if (character && current == '\'') character = false;
            } else if (current == '/' && next == '/') {
                result.append("//"); index += 2; lineComment = true;
            } else if (current == '/' && next == '*') {
                result.append("/*"); index += 2; blockComment = true;
            } else if (current == '"') { result.append(current); index++; string = true;
            } else if (current == '\'') { result.append(current); index++; character = true;
            } else if (source.startsWith("@" + oldName, index)
                    && (index + oldName.length() + 1 == source.length()
                    || !Character.isJavaIdentifierPart(source.charAt(index + oldName.length() + 1)))) {
                result.append('@').append(newName); index += oldName.length() + 1;
            } else { result.append(current); index++; }
        }
        return result.toString();
    }

    private static void rewriteNacosConfig(Path root, Path file, Set<String> changed, List<String> rules)
            throws IOException {
        String before = Files.readString(file, StandardCharsets.UTF_8);
        if (!before.contains("nacos") || before.contains("spring.config.import")
                || before.contains("config:\n    import:")) return;
        String entry = file.getFileName().toString().endsWith(".properties")
                ? "\nspring.config.import=optional:nacos:${spring.application.name}.${spring.cloud.nacos.config.file-extension:yaml}\n"
                : "\nspring.config.import: optional:nacos:${spring.application.name}.${spring.cloud.nacos.config.file-extension:yaml}\n";
        Files.writeString(file, before + entry, StandardCharsets.UTF_8);
        changed.add(relative(root, file));
        rules.add("NACOS_CONFIG_DATA_IMPORT");
    }

    private static void rewriteDubboXml(Path root, Path file, Set<String> changed,
                                        List<String> rules, List<String> blockers) throws IOException {
        String content = Files.readString(file, StandardCharsets.UTF_8);
        if (!content.contains("<dubbo:")) return;
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            Document document;
            try (var input = Files.newInputStream(file)) {
                document = factory.newDocumentBuilder().parse(input);
            }
            List<Element> elements = dubboElements(document);
            if (elements.isEmpty()) return;
            List<String> unsupported = new ArrayList<>();
            for (Element element : elements) {
                String kind = element.getLocalName();
                if ("service".equals(kind)
                        && (element.getAttribute("interface").isBlank() || element.getAttribute("ref").isBlank())) {
                    unsupported.add(element.getTagName() + " requires interface and ref");
                } else if ("reference".equals(kind) && element.getAttribute("interface").isBlank()) {
                    unsupported.add(element.getTagName() + " requires interface");
                }
                for (int i = 0; i < element.getAttributes().getLength(); i++) {
                    Node attribute = element.getAttributes().item(i);
                    if (!supportedAttribute(element.getLocalName(), attribute.getNodeName())) {
                        unsupported.add(element.getTagName() + "@" + attribute.getNodeName());
                    }
                }
            }
            if (!unsupported.isEmpty()) {
                blockers.add(relative(root, file) + ": unsupported Dubbo XML attributes " + unsupported
                        + "; descriptor retained to prevent a semantic drop");
                return;
            }

            String classStem = javaIdentifier(file.getFileName().toString().replaceFirst("\\.xml$", ""));
            String className = Character.toUpperCase(classStem.charAt(0)) + classStem.substring(1)
                    + "DubboConfiguration";
            String source = generateDubboConfiguration(className, elements);
            Path generated = root.resolve("src/main/java/io/elmos/generated/dubbo").resolve(className + ".java");
            Files.createDirectories(generated.getParent());
            if (!Files.exists(generated) || !Files.readString(generated, StandardCharsets.UTF_8).equals(source)) {
                Files.writeString(generated, source, StandardCharsets.UTF_8);
                changed.add(relative(root, generated));
            }

            for (Element element : elements) {
                Node parent = element.getParentNode();
                parent.replaceChild(document.createComment(" migrated by ELMOS to " + className + " "), element);
            }
            TransformerFactory transformers = TransformerFactory.newInstance();
            transformers.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
            transformers.setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "");
            var transformer = transformers.newTransformer();
            transformer.setOutputProperty(OutputKeys.INDENT, "yes");
            transformer.transform(new DOMSource(document), new StreamResult(file.toFile()));
            changed.add(relative(root, file));
            rules.add("DUBBO_XML_TO_TYPED_JAVA_CONFIG");
        } catch (Exception error) {
            blockers.add(relative(root, file) + ": Dubbo XML could not be safely parsed: "
                    + error.getClass().getSimpleName());
        }
    }

    private static List<Element> dubboElements(Document document) {
        List<Element> values = new ArrayList<>();
        NodeList all = document.getElementsByTagName("*");
        for (int index = 0; index < all.getLength(); index++) {
            if (!(all.item(index) instanceof Element element)) continue;
            String prefix = element.getPrefix();
            String namespace = element.getNamespaceURI();
            if ("dubbo".equals(prefix) || (namespace != null && namespace.contains("dubbo"))) {
                values.add(element);
            }
        }
        return values;
    }

    private static boolean supportedAttribute(String kind, String name) {
        if (name.startsWith("xmlns")) return true;
        return switch (kind) {
            case "application" -> Set.of("id", "name", "owner", "organization").contains(name);
            case "registry" -> Set.of("id", "address", "protocol", "username", "password", "check").contains(name);
            case "protocol" -> Set.of("id", "name", "port", "host", "threads").contains(name);
            case "service" -> Set.of("id", "interface", "ref", "version", "group", "timeout", "retries").contains(name);
            case "reference" -> Set.of("id", "interface", "version", "group", "timeout", "retries", "check").contains(name);
            default -> false;
        };
    }

    private static String generateDubboConfiguration(String className, List<Element> elements) {
        StringBuilder source = new StringBuilder("""
                package io.elmos.generated.dubbo;

                import org.apache.dubbo.config.ApplicationConfig;
                import org.apache.dubbo.config.ProtocolConfig;
                import org.apache.dubbo.config.ReferenceConfig;
                import org.apache.dubbo.config.RegistryConfig;
                import org.apache.dubbo.config.ServiceConfig;
                import org.springframework.beans.factory.annotation.Qualifier;
                import org.springframework.context.annotation.Bean;
                import org.springframework.context.annotation.Configuration;

                @Configuration
                public class %s {
                """.formatted(className));
        int sequence = 0;
        for (Element element : elements) {
            String kind = element.getLocalName();
            String id = value(element, "id", "legacyDubbo" + Character.toUpperCase(kind.charAt(0))
                    + kind.substring(1) + (++sequence));
            String method = javaIdentifier(id);
            switch (kind) {
                case "application" -> {
                    source.append("    @Bean(name = \"").append(javaString(id)).append("\")\n")
                            .append("    ApplicationConfig ").append(method).append("() {\n")
                            .append("        ApplicationConfig config = new ApplicationConfig();\n");
                    setter(source, "Name", element.getAttribute("name"), false);
                    setter(source, "Owner", element.getAttribute("owner"), false);
                    setter(source, "Organization", element.getAttribute("organization"), false);
                    source.append("        return config;\n    }\n\n");
                }
                case "registry" -> {
                    source.append("    @Bean(name = \"").append(javaString(id)).append("\")\n")
                            .append("    RegistryConfig ").append(method).append("() {\n")
                            .append("        RegistryConfig config = new RegistryConfig();\n");
                    setter(source, "Address", element.getAttribute("address"), false);
                    setter(source, "Protocol", element.getAttribute("protocol"), false);
                    setter(source, "Username", element.getAttribute("username"), false);
                    setter(source, "Password", element.getAttribute("password"), false);
                    setter(source, "Check", element.getAttribute("check"), true);
                    source.append("        return config;\n    }\n\n");
                }
                case "protocol" -> {
                    source.append("    @Bean(name = \"").append(javaString(id)).append("\")\n")
                            .append("    ProtocolConfig ").append(method).append("() {\n")
                            .append("        ProtocolConfig config = new ProtocolConfig();\n");
                    setter(source, "Name", element.getAttribute("name"), false);
                    setter(source, "Host", element.getAttribute("host"), false);
                    setter(source, "Port", element.getAttribute("port"), true);
                    setter(source, "Threads", element.getAttribute("threads"), true);
                    source.append("        return config;\n    }\n\n");
                }
                case "service" -> {
                    String ref = element.getAttribute("ref");
                    source.append("    @Bean(name = \"").append(javaString(id)).append("\")\n")
                            .append("    ServiceConfig<Object> ").append(method).append("(@Qualifier(\"")
                            .append(javaString(ref)).append("\") Object implementation) {\n")
                            .append("        ServiceConfig<Object> config = new ServiceConfig<>();\n")
                            .append("        config.setInterface(\"").append(javaString(element.getAttribute("interface"))).append("\");\n")
                            .append("        config.setRef(implementation);\n");
                    commonServiceSetters(source, element);
                    source.append("        return config;\n    }\n\n");
                }
                case "reference" -> {
                    source.append("    @Bean(name = \"").append(javaString(id)).append("\")\n")
                            .append("    ReferenceConfig<Object> ").append(method).append("() {\n")
                            .append("        ReferenceConfig<Object> config = new ReferenceConfig<>();\n")
                            .append("        config.setInterface(\"").append(javaString(element.getAttribute("interface"))).append("\");\n");
                    commonServiceSetters(source, element);
                    setter(source, "Check", element.getAttribute("check"), true);
                    source.append("        return config;\n    }\n\n");
                }
                default -> throw new IllegalArgumentException("unsupported Dubbo XML element " + kind);
            }
        }
        return source.append("}\n").toString();
    }

    private static void commonServiceSetters(StringBuilder source, Element element) {
        setter(source, "Version", element.getAttribute("version"), false);
        setter(source, "Group", element.getAttribute("group"), false);
        setter(source, "Timeout", element.getAttribute("timeout"), true);
        setter(source, "Retries", element.getAttribute("retries"), true);
    }

    private static void setter(StringBuilder source, String property, String value, boolean scalar) {
        if (value == null || value.isBlank()) return;
        source.append("        config.set").append(property).append('(');
        if (scalar && value.matches("-?\\d+")) source.append(value);
        else if (scalar && (value.equals("true") || value.equals("false"))) source.append(value);
        else source.append('"').append(javaString(value)).append('"');
        source.append(");\n");
    }

    private static String value(Element element, String name, String fallback) {
        String value = element.getAttribute(name);
        return value == null || value.isBlank() ? fallback : value;
    }

    private static String javaIdentifier(String value) {
        String normalized = value.replaceAll("[^A-Za-z0-9_$]", "_");
        if (normalized.isBlank()) normalized = "legacyDubboBean";
        if (!Character.isJavaIdentifierStart(normalized.charAt(0))) normalized = "bean_" + normalized;
        return normalized;
    }

    private static String javaString(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\r", "\\r").replace("\n", "\\n");
    }

    private static String relative(Path root, Path file) {
        return root.relativize(file).toString().replace('\\', '/');
    }
}
