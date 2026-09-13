package io.elmos.worker.jpa;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import java.io.IOException;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** Converts the safe, deterministic subset of Hibernate {@code *.hbm.xml} to Jakarta JPA entities. */
public final class HibernateHbmXmlToJpaConverter {
    public record MappingResult(
            boolean modified,
            Set<String> generatedFiles,
            Map<String, String> sourceToTarget,
            List<String> blockingObligations
    ) {}

    private static final Map<String, String> TYPES = Map.ofEntries(
            Map.entry("long", "Long"), Map.entry("java.lang.Long", "Long"),
            Map.entry("integer", "Integer"), Map.entry("int", "Integer"),
            Map.entry("string", "String"), Map.entry("java.lang.String", "String"),
            Map.entry("boolean", "Boolean"), Map.entry("yes_no", "Boolean"),
            Map.entry("timestamp", "java.time.Instant"), Map.entry("date", "java.time.LocalDate"),
            Map.entry("big_decimal", "java.math.BigDecimal"), Map.entry("java.math.BigDecimal", "java.math.BigDecimal"),
            Map.entry("uuid-char", "java.util.UUID"), Map.entry("uuid-binary", "java.util.UUID")
    );

    private HibernateHbmXmlToJpaConverter() {}

    public static MappingResult convert(Path projectRoot, Path outputJavaRoot) {
        Objects.requireNonNull(projectRoot, "projectRoot must not be null");
        Objects.requireNonNull(outputJavaRoot, "outputJavaRoot must not be null");
        Set<String> generated = new LinkedHashSet<>();
        Map<String, String> mappings = new LinkedHashMap<>();
        List<String> blockers = new ArrayList<>();
        if (!Files.isDirectory(projectRoot)) {
            return new MappingResult(false, generated, mappings, List.of("project root does not exist"));
        }
        try (var files = Files.walk(projectRoot)) {
            for (Path hbm : files.filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().endsWith(".hbm.xml")).toList()) {
                convertFile(projectRoot, outputJavaRoot, hbm, generated, mappings, blockers);
            }
        } catch (Exception e) {
            blockers.add("HBM scan failed: " + e.getClass().getSimpleName());
        }
        return new MappingResult(!generated.isEmpty(), Set.copyOf(generated), Map.copyOf(mappings), List.copyOf(blockers));
    }

    private static void convertFile(
            Path projectRoot,
            Path outputRoot,
            Path hbm,
            Set<String> generated,
            Map<String, String> mappings,
            List<String> blockers
    ) {
        String relative = relative(projectRoot, hbm);
        try {
            String xml = Files.readString(hbm, StandardCharsets.UTF_8);
            Document document = secureFactory().newDocumentBuilder().parse(new InputSource(new StringReader(xml)));
            Element root = document.getDocumentElement();
            String defaultPackage = root.getAttribute("package").trim();
            for (Element classElement : children(root, "class")) {
                String declaredName = required(classElement, "name");
                String fqcn = declaredName.contains(".") || defaultPackage.isBlank()
                        ? declaredName : defaultPackage + "." + declaredName;
                String className = fqcn.substring(fqcn.lastIndexOf('.') + 1);
                String packageName = fqcn.contains(".") ? fqcn.substring(0, fqcn.lastIndexOf('.')) : "";
                if (!javaIdentifier(className) || (!packageName.isBlank() && !javaPackage(packageName))) {
                    blockers.add(relative + ": invalid mapped class name " + fqcn);
                    continue;
                }
                List<String> localBlockers = unsupported(classElement);
                List<Field> fields = parseFields(classElement, localBlockers);
                if (!localBlockers.isEmpty()) {
                    localBlockers.forEach(reason -> blockers.add(relative + ": " + fqcn + ": " + reason));
                    continue;
                }
                String table = classElement.getAttribute("table").trim();
                String source = render(packageName, className, table, fields);
                Path target = outputRoot.resolve(fqcn.replace('.', '/') + ".java").normalize();
                if (!target.startsWith(outputRoot.normalize())) {
                    blockers.add(relative + ": target path escaped output root");
                    continue;
                }
                if (Files.exists(target)) {
                    blockers.add(relative + ": target entity already exists: " + relative(outputRoot, target));
                    continue;
                }
                Files.createDirectories(target.getParent());
                Files.writeString(target, source, StandardCharsets.UTF_8);
                String targetRelative = relative(outputRoot, target);
                generated.add(targetRelative);
                mappings.put(relative + "#" + fqcn, targetRelative);
            }
        } catch (Exception e) {
            blockers.add(relative + ": unsafe or invalid HBM XML: " + e.getClass().getSimpleName());
        }
    }

    private static DocumentBuilderFactory secureFactory() throws Exception {
        DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
        factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
        factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        factory.setXIncludeAware(false);
        factory.setExpandEntityReferences(false);
        return factory;
    }

    private static List<String> unsupported(Element element) {
        List<String> blockers = new ArrayList<>();
        for (String tag : List.of("composite-id", "joined-subclass", "union-subclass", "subclass", "component", "dynamic-component", "any")) {
            if (!children(element, tag).isEmpty()) {
                blockers.add(tag + " requires an explicit inheritance/value-object mapping contract");
            }
        }
        return blockers;
    }

    private static List<Field> parseFields(Element classElement, List<String> blockers) {
        List<Field> fields = new ArrayList<>();
        for (Element id : children(classElement, "id")) {
            fields.add(scalarField(id, true, blockers));
        }
        for (Element property : children(classElement, "property")) {
            fields.add(scalarField(property, false, blockers));
        }
        for (Element relation : children(classElement, "many-to-one")) {
            String name = required(relation, "name");
            String target = required(relation, "class");
            String column = column(relation, name + "_id");
            if (!javaIdentifier(name) || target.isBlank()) {
                blockers.add("invalid many-to-one mapping " + name);
            }
            fields.add(new Field(name, target, column, "MANY_TO_ONE", false, false));
        }
        return fields;
    }

    private static Field scalarField(Element element, boolean id, List<String> blockers) {
        String name = required(element, "name");
        String sourceType = element.getAttribute("type").trim();
        if (sourceType.isBlank() && id) {
            sourceType = "long";
        }
        String targetType = TYPES.get(sourceType);
        if (!javaIdentifier(name) || targetType == null) {
            blockers.add("unsupported scalar mapping " + name + " type=" + sourceType);
            targetType = "Object";
        }
        boolean generated = false;
        if (id && !children(element, "generator").isEmpty()) {
            String strategy = children(element, "generator").get(0).getAttribute("class").trim();
            if (strategy.equals("identity")) generated = true;
            else if (!strategy.equals("assigned")) {
                blockers.add("identifier generator " + strategy
                        + " is provider-specific and requires an explicit JPA generator contract");
            }
        }
        return new Field(name, targetType, column(element, name), "SCALAR", id, generated);
    }

    private static String render(String packageName, String className, String table, List<Field> fields) {
        StringBuilder out = new StringBuilder();
        if (!packageName.isBlank()) {
            out.append("package ").append(packageName).append(";\n\n");
        }
        out.append("import jakarta.persistence.*;\n\n@Entity\n");
        if (!table.isBlank()) {
            out.append("@Table(name = \"").append(escape(table)).append("\")\n");
        }
        out.append("public class ").append(className).append(" {\n");
        for (Field field : fields) {
            if (field.id) out.append("    @Id\n");
            if (field.generated) out.append("    @GeneratedValue(strategy = GenerationType.IDENTITY)\n");
            if (field.kind.equals("MANY_TO_ONE")) {
                out.append("    @ManyToOne(fetch = FetchType.LAZY, optional = false)\n")
                        .append("    @JoinColumn(name = \"").append(escape(field.column)).append("\", nullable = false)\n");
            } else {
                out.append("    @Column(name = \"").append(escape(field.column)).append("\")\n");
            }
            out.append("    private ").append(field.type).append(' ').append(field.name).append(";\n\n");
        }
        out.append("    protected ").append(className).append("() {}\n");
        for (Field field : fields) {
            String suffix = Character.toUpperCase(field.name.charAt(0)) + field.name.substring(1);
            out.append("\n    public ").append(field.type).append(" get").append(suffix)
                    .append("() { return ").append(field.name).append("; }\n")
                    .append("    public void set").append(suffix).append('(').append(field.type).append(' ')
                    .append(field.name).append(") { this.").append(field.name).append(" = ").append(field.name).append("; }\n");
        }
        return out.append("}\n").toString();
    }

    private static String column(Element element, String fallback) {
        String direct = element.getAttribute("column").trim();
        if (!direct.isBlank()) return direct;
        List<Element> nested = children(element, "column");
        return nested.isEmpty() ? fallback : nested.get(0).getAttribute("name").trim();
    }

    private static List<Element> children(Element parent, String tag) {
        List<Element> result = new ArrayList<>();
        NodeList nodes = parent.getChildNodes();
        for (int i = 0; i < nodes.getLength(); i++) {
            Node node = nodes.item(i);
            if (node instanceof Element element && (element.getTagName().equals(tag)
                    || element.getTagName().endsWith(":" + tag))) {
                result.add(element);
            }
        }
        return result;
    }

    private static String required(Element element, String attribute) {
        return element.getAttribute(attribute).trim();
    }

    private static boolean javaIdentifier(String value) {
        if (value.isBlank() || !Character.isJavaIdentifierStart(value.charAt(0))) return false;
        return value.chars().skip(1).allMatch(Character::isJavaIdentifierPart);
    }

    private static boolean javaPackage(String value) {
        for (String part : value.split("\\.")) if (!javaIdentifier(part)) return false;
        return true;
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private static String relative(Path root, Path file) {
        return root.relativize(file).toString().replace('\\', '/');
    }

    private record Field(String name, String type, String column, String kind, boolean id, boolean generated) {}
}
